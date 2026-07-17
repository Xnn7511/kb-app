#!/usr/bin/env python3
"""
批量导入厂商资料到知识库
1. 清空现有数据
2. 解析所有PDF
3. AI分类
4. 建立向量索引
"""
import sys
import os
import shutil
from pathlib import Path

sys.path.insert(0, '/workspace/polymer-kb/backend')

from database import (
    init_db, get_db, add_document, get_doc_by_checksum,
    list_documents, get_document
)
from file_parser import parse_file, compute_checksum
from rag_engine import rag_engine

UPLOADS_DIR = Path('/root/uploads')
RAW_DIR = Path('/workspace/polymer-kb/uploads/raw')
CHROMA_DIR = Path('/workspace/polymer-kb/data/chroma')
DB_PATH = Path('/workspace/polymer-kb/data/config/polymer_kb.db')


def clear_all_data():
    """清空所有数据"""
    print("=" * 60)
    print("🗑  清空现有数据...")
    print("=" * 60)

    # 清空向量数据库
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
        print("  ✅ 向量数据库已清空")

    # 清空SQLite数据库
    if DB_PATH.exists():
        DB_PATH.unlink()
        print("  ✅ SQLite数据库已清空")

    # 清空原始文件
    if RAW_DIR.exists():
        for f in RAW_DIR.iterdir():
            if f.is_file():
                f.unlink()
        print("  ✅ 原始文件目录已清空")

    # 重新初始化
    init_db()
    print("  ✅ 数据库重新初始化")

    # 重置RAG引擎的集合
    try:
        rag_engine._collection = None
        rag_engine._chroma_client = None
        print("  ✅ RAG引擎已重置")
    except Exception as e:
        print(f"  ⚠️ RAG重置: {e}")


def import_pdfs():
    """导入所有PDF文件"""
    pdf_files = sorted(UPLOADS_DIR.glob('*.pdf'))
    print(f"\n{'=' * 60}")
    print(f"📥 开始导入 {len(pdf_files)} 份PDF资料")
    print(f"{'=' * 60}\n")

    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        # 提取原始文件名（去掉时间戳前缀）
        original_name = pdf_path.name
        # 尝试提取有意义的文件名
        if '-' in original_name:
            parts = original_name.split('-', 1)
            if len(parts) == 2 and len(parts[0]) > 10:
                display_name = parts[1]
            else:
                display_name = original_name
        else:
            display_name = original_name

        print(f"[{i:2d}/{len(pdf_files)}] 📄 {display_name}")

        # 复制到raw目录
        raw_path = RAW_DIR / display_name
        try:
            shutil.copy2(pdf_path, raw_path)
        except Exception as e:
            print(f"       ❌ 复制失败: {e}")
            fail_count += 1
            continue

        # 计算checksum
        checksum = compute_checksum(str(raw_path))

        # 检查重复
        existing = get_doc_by_checksum(checksum)
        if existing:
            print(f"       ⏭ 已存在，跳过")
            skip_count += 1
            continue

        # 解析PDF
        try:
            text_content, file_type = parse_file(str(raw_path))
            file_size = raw_path.stat().st_size
        except Exception as e:
            print(f"       ❌ 解析失败: {e}")
            fail_count += 1
            continue

        # 提取标题（从文件名）
        title = raw_path.stem

        # AI自动分类
        print(f"       🤖 AI分类中...", end='')
        try:
            metadata = rag_engine.auto_classify(title, text_content)
            mat_types = metadata.get('material_types', [])
            func_tags = metadata.get('function_tags', [])
            print(f" ✅")
            print(f"       📌 材料: {', '.join(mat_types) if mat_types else '未识别'}")
            print(f"       🏷 功效: {', '.join(func_tags) if func_tags else '未识别'}")
        except Exception as e:
            print(f" ⚠️ 分类失败: {e}")
            mat_types = []
            func_tags = []

        # 保存到数据库
        try:
            doc_id = add_document(
                filename=display_name,
                title=metadata.get('title', title),
                summary=metadata.get('summary', text_content[:300]),
                material_types=mat_types,
                function_tags=func_tags,
                file_type=file_type,
                file_size=file_size,
                content_text=text_content,
                checksum=checksum,
            )
        except Exception as e:
            print(f"       ❌ 数据库保存失败: {e}")
            fail_count += 1
            continue

        # 向量索引
        try:
            chunk_count = rag_engine.index_document(doc_id, text_content)
            print(f"       🔍 索引完成 ({chunk_count} chunks, ID:{doc_id})")
        except Exception as e:
            print(f"       ⚠️ 索引失败: {e}")

        success_count += 1
        print()

    print(f"{'=' * 60}")
    print(f"📊 导入完成: 成功 {success_count} | 跳过 {skip_count} | 失败 {fail_count}")
    print(f"{'=' * 60}")

    # 显示最终统计
    docs = list_documents()
    print(f"\n📚 知识库当前共 {len(docs)} 份资料")

    # 按材料类型统计
    from collections import Counter
    all_types = []
    all_funcs = []
    for doc in docs:
        all_types.extend(doc.get('material_types', []))
        all_funcs.extend(doc.get('function_tags', []))

    if all_types:
        print(f"\n📌 材料类型分布:")
        for t, c in Counter(all_types).most_common():
            print(f"   {t}: {c}份")

    if all_funcs:
        print(f"\n🏷 功效标签分布:")
        for f, c in Counter(all_funcs).most_common():
            print(f"   {f}: {c}份")


if __name__ == '__main__':
    # 确保目录存在
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 清空并导入
    clear_all_data()
    import_pdfs()
