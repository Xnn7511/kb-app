"""
高分子材料原料知识库 - 加载示例数据
此脚本在首次启动时运行，将 uploads/raw 中的文件索引到系统
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database import init_db, get_doc_by_checksum, add_document, list_documents
from file_parser import parse_file, compute_checksum
from rag_engine import rag_engine


def load_demo_data():
    """加载 uploads/raw 中的示例数据"""
    init_db()

    raw_dir = Path(__file__).resolve().parent.parent / "uploads" / "raw"
    if not raw_dir.exists():
        print(f"原始资料目录不存在: {raw_dir}")
        return

    files = list(raw_dir.glob("*"))
    if not files:
        print("没有找到资料文件")
        return

    print(f"找到 {len(files)} 个文件待处理...")

    for filepath in files:
        if filepath.is_dir():
            continue
        if filepath.name.startswith('.'):
            continue

        ext = filepath.suffix.lower()
        if ext not in {'.pdf', '.docx', '.doc', '.txt', '.md', '.csv', '.xlsx', '.xls'}:
            continue

        print(f"\n处理: {filepath.name}")

        # 计算 checksum
        checksum = compute_checksum(str(filepath))

        # 检查是否已存在
        existing = get_doc_by_checksum(checksum)
        if existing:
            print(f"  ⏭ 已存在 (ID: {existing['id']})，跳过")
            continue

        # 解析文件
        text_content, file_type = parse_file(str(filepath))
        file_size = filepath.stat().st_size

        # AI 分类
        title = filepath.stem
        print(f"  🤖 正在 AI 分类...")
        metadata = rag_engine.auto_classify(title, text_content)
        print(f"  标题: {metadata.get('title', title)}")
        print(f"  材料类型: {metadata.get('material_types', [])}")
        print(f"  功效标签: {metadata.get('function_tags', [])}")

        # 保存到数据库
        doc_id = add_document(
            filename=filepath.name,
            title=metadata.get("title", title),
            summary=metadata.get("summary", text_content[:200]),
            material_types=metadata.get("material_types", []),
            function_tags=metadata.get("function_tags", []),
            file_type=file_type,
            file_size=file_size,
            content_text=text_content,
            checksum=checksum,
        )

        # 索引到向量数据库
        try:
            chunk_count = rag_engine.index_document(doc_id, text_content)
            print(f"  ✅ 索引完成 (ID: {doc_id}, {chunk_count} chunks)")
        except Exception as e:
            print(f"  ⚠️ 索引失败: {e}")

    print("\n✅ 示例数据加载完成！")
    docs = list_documents()
    print(f"当前知识库共 {len(docs)} 份资料")


if __name__ == "__main__":
    load_demo_data()
