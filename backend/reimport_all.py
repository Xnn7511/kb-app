#!/usr/bin/env python3
"""批量重新导入全部厂商资料 - v3 增强版（OCR + 厂家 + 智能摘要）"""
import sys, os, shutil, json

# 减少 HuggingFace 重试次数，避免 504 超时阻塞
os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '15'
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'

from pathlib import Path

sys.path.insert(0, '/workspace/polymer-kb/backend')

from database import (init_db, add_document, get_doc_by_checksum, list_documents)
from file_parser import (parse_file, compute_checksum, detect_language,
                         extract_tds_data, extract_manufacturer, generate_smart_summary, _clean_text,
                         translate_en_title, EN_ZH_MAP)
from rag_engine import rag_engine

UPLOADS_DIR = Path('/root/uploads')
RAW_DIR = Path('/workspace/polymer-kb/uploads/raw')
CHROMA_DIR = Path('/workspace/polymer-kb/data/chroma')
DB_PATH = Path('/workspace/polymer-kb/data/polymer_kb.db')


def clear_all():
    print("🗑 清空...")
    for d in [DB_PATH, CHROMA_DIR, RAW_DIR]:
        try:
            if d.is_dir(): shutil.rmtree(d)
            elif d.exists(): d.unlink()
        except: pass
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    rag_engine._collection = None
    rag_engine._chroma_client = None
    print("✅ 已清空\n")


def classify(text, title):
    t = (text + ' ' + title).lower()
    mat_map = {
        '热塑性': ['pp','聚乙烯','聚丙烯','pe','ps','pvc','pet','pa','pc','abs','tpe','tpo','poe','eva','coc','聚烯烃','polypropylene','polyethylene','evolue'],
        '弹性体': ['弹性体','tpe','tpo','poe','epdm','sebs','sbs','橡胶','丁烯','tafmer','elastomer','ethylene-butene','乙烯-丁烯'],
        '工程塑料': ['pa66','pa6','pbt','pom','pps','lcp','peek','pc','工程塑料'],
        '通用塑料': ['pp','pe','pvc','ps','abs','通用塑料','聚丙烯','聚乙烯'],
        '胶粘剂': ['胶','adhesive','粘合','粘结','粘着','orevac','bynel','相容剂','接枝','grafted','tie resin'],
        '母料': ['母料','母粒','masterbatch','concentrate','polybatch','constab','abvt'],
        '功能材料': ['功能','functional','specialty','特种'],
        '生物基材料': ['生物','bio','降解','degradable','可降解','biodegradable'],
        '复合材料': ['复合','composite','增强','玻纤','碳纤维','填料','填充'],
    }
    func_map = {
        '增韧': ['增韧','toughen','韧性','impact','冲击','弹性','poe','tpe','tafmer','丁烯','elastomer'],
        '增强': ['增强','reinforce','玻纤','gf','强度','strength','刚性','模量','modulus'],
        '阻燃': ['阻燃','flame','fire','fr','v0','ul94','防火'],
        '抗静电': ['抗静电','antistatic','静电','esd'],
        '耐磨': ['耐磨','wear','abrasion','润滑'],
        '耐候': ['耐候','weather','uv','紫外','抗老化'],
        '低翘曲': ['翘曲','warp','尺寸稳定'],
        '耐高温': ['耐高温','heat resistant','hdt','热变形','耐热','high temp'],
        '耐化学': ['耐化学','chemical','耐油','耐溶剂'],
        '绝缘': ['绝缘','insulation','介电','电气'],
        '抗UV': ['uv','紫外','光稳定','耐候'],
        '透明': ['透明','clear','transparen','光学','雾度','haze','gloss','光泽'],
        '可降解': ['降解','degradable','生物','bio','环保'],
        '高光泽': ['高光泽','gloss','光泽','高亮'],
        '爽滑': ['爽滑','slip','润滑','摩擦','开口','coefficient of friction'],
        '防雾': ['防雾','antifog','fog','雾'],
        '消光': ['消光','matte','哑光','雾面','matt'],
        '珠光': ['珠光','pearl','闪烁','金属光泽'],
        '增白': ['增白','white','白度','荧光','bright'],
        '抗粘': ['抗粘','anti-block','防粘','粘连','block','开口','anti block'],
        '防粘结': ['防粘结','anti-block','防粘','粘连','block'],
        '相容': ['相容','compatibil','接枝','改性','增容','coupling'],
        '着色': ['着色','color','色母','颜料','染料'],
    }
    mat, func = [], []
    for mt, ks in mat_map.items():
        for k in ks:
            if k in t: mat.append(mt); break
    for ft, ks in func_map.items():
        for k in ks:
            if k in t: func.append(ft); break
    if '母料' in title or 'masterbatch' in t.split(): mat.append('母料')
    if 'pp' in t or '聚丙烯' in title:
        for m in ['热塑性','通用塑料']:
            if m not in mat: mat.append(m)
    if not mat: mat = ['其他']
    if not func: func = ['其他']
    return mat, func


def main():
    clear_all()
    pdfs = sorted(UPLOADS_DIR.glob('*.pdf'))
    print(f"📥 处理 {len(pdfs)} 份PDF\n{'='*60}")

    ok = skip = fail = en_count = 0

    for i, pp in enumerate(pdfs, 1):
        name = pp.name
        dn = name.split('-', 1)[1] if '-' in name and len(name.split('-', 1)[0]) > 10 else name
        print(f"[{i:2d}/{len(pdfs)}] {dn}")

        rp = RAW_DIR / dn
        shutil.copy2(pp, rp)
        cs = compute_checksum(str(rp))
        if get_doc_by_checksum(cs):
            print(f"    ⏭ 跳过"); skip += 1; continue

        text, ft = parse_file(str(rp))
        size = rp.stat().st_size
        lang = detect_language(text)
        tds = extract_tds_data(text)
        mfr = extract_manufacturer(rp.stem, text)
        mat, func = classify(text, rp.stem)
        summary = generate_smart_summary(text, tds)

        # 英文文档：翻译标题并填充 content_zh
        title_zh = rp.stem
        content_zh = ''
        if lang in ('en', 'mixed'):
            title_zh = translate_en_title(rp.stem)
            # 对摘要中的英文关键词也做翻译
            summary = translate_en_title(summary)
            # 尝试翻译文本前500字符作为 content_zh 预览
            content_zh = translate_en_title(text[:500])
            en_count += 1

        tds_str = " | ".join(f"{k}={v}" for k,v in tds.items() if v is not None)[:80]
        print(f"    🏭 {mfr or '未识别'} | 📌 {','.join(mat[:3])} | 🏷 {','.join(func[:3])} | 🌐 {lang}")
        if tds_str: print(f"    📊 {tds_str}")
        print(f"    📝 摘要: {summary[:100]}")
        if len(text) < 100: print(f"    ⚠️ 文本{len(text)}字符 - 图片型PDF")

        did = add_document(
            filename=dn, title=title_zh, manufacturer=mfr, summary=summary,
            material_types=mat, function_tags=func,
            file_type=ft, file_size=size, content_text=text, content_zh=content_zh,
            tds_data=tds, language=lang, checksum=cs)

        if len(text) >= 50:
            try:
                cc = rag_engine.index_document(did, text)
                print(f"    🔍 {cc} chunks (ID:{did})")
            except Exception as e:
                print(f"    ⚠️ 索引失败: {e}")
        else:
            print(f"    ⏭ 跳过索引 ID:{did}")
        ok += 1
        print()

    print(f"{'='*60}")
    print(f"📊 成功 {ok} | 跳过 {skip} | 英文 {en_count}")
    docs = list_documents()
    print(f"📚 知识库共 {len(docs)} 份")


if __name__ == '__main__':
    main()
