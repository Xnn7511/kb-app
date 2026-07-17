#!/usr/bin/env python3
"""
基于文件名和内容的规则分类脚本
为所有文档自动打上材料类型和功效标签
"""
import sys
import re
import json
from pathlib import Path

sys.path.insert(0, '/workspace/polymer-kb/backend')
from database import get_db, list_documents, update_document

# 材料类型关键词映射
MATERIAL_KEYWORDS = {
    '热塑性': ['PP', '聚乙烯', '聚丙烯', 'PE', 'PS', 'PVC', 'PET', 'PA', 'PC', 'ABS', 'TPE', 'TPO', 'POE', 'EVA', 'COC', '环烯烃'],
    '热固性': ['环氧树脂', '酚醛', '聚氨酯', 'PU', '不饱和聚酯', 'UP'],
    '弹性体': ['弹性体', 'TPE', 'TPO', 'POE', 'EPDM', 'SEBS', 'SBS', '橡胶', '丁烯', 'TAFMER'],
    '工程塑料': ['PA', 'PC', 'PBT', 'POM', 'PPS', 'LCP', 'PEEK', '工程塑料', '特种工程塑料'],
    '通用塑料': ['PP', 'PE', 'PVC', 'PS', 'ABS', '通用塑料'],
    '胶粘剂': ['胶', ' adhesive', '粘合', '粘结', '粘着', 'orevac', 'bynel', '相容剂', '接枝'],
    '涂料': ['涂料', '油漆', '涂层', 'coating', 'paint'],
    '母料': ['母料', '母粒', 'masterbatch', 'MB', 'concentrate'],
    '功能材料': ['功能', 'functional', '特种', 'specialty'],
    '生物基材料': ['生物', 'bio', '降解', 'degradable', '可降解', '环保'],
    '复合材料': ['复合', 'composite', '增强', '玻纤', '碳纤维', '填料'],
}

# 功效标签关键词映射
FUNCTION_KEYWORDS = {
    '增韧': ['增韧', 'toughen', '韧性', '冲击', 'impact', '弹性', '弹性体', 'POE', 'TPE', 'TAFMER', '丁烯'],
    '增强': ['增强', 'reinforce', '玻纤', 'GF', '碳纤维', '强度', 'strength', '刚性', '模量'],
    '阻燃': ['阻燃', 'flame', 'fire', 'FR', 'V0', 'UL94', '防火', '难燃'],
    '导电': ['导电', 'conductive', '抗静电', '静电', 'ESD', 'EMI'],
    '导热': ['导热', 'thermal', '散热', 'heat'],
    '耐磨': ['耐磨', 'wear', '摩擦', 'abrasion', '润滑'],
    '耐候': ['耐候', 'weather', 'UV', '紫外', '抗老化', '抗UV', '光稳定'],
    '低翘曲': ['低翘曲', 'low warp', '翘曲', 'warp', '尺寸稳定'],
    '耐高温': ['耐高温', 'heat resistant', 'HDT', '热变形', '耐热'],
    '耐低温': ['耐低温', 'cold', '低温', '脆化'],
    '耐化学': ['耐化学', 'chemical', '耐油', '耐溶剂', '耐腐蚀'],
    '绝缘': ['绝缘', 'insulation', '介电', '电气'],
    '抗静电': ['抗静电', 'antistatic', '静电', 'ESD'],
    '抗菌': ['抗菌', 'antibacterial', '抑菌', ' antimicrobial'],
    '抗UV': ['抗UV', 'UV', '紫外', '光稳定', '耐候'],
    '透明': ['透明', 'clear', 'transparen', '光学', '雾度', 'haze', '光泽', 'gloss'],
    '轻量化': ['轻量化', 'light', '减重', '低密度', '发泡', 'foam'],
    '可降解': ['降解', 'degradable', '生物', 'bio', '环保', '绿色'],
    '低VOC': ['低VOC', 'VOC', '低气味', '低散发', 'odor'],
    '高光泽': ['高光泽', 'gloss', '光泽', '镜面', '高亮'],
    '爽滑': ['爽滑', 'slip', '润滑', '摩擦', '开口'],
    '防雾': ['防雾', 'antifog', '雾', 'fog'],
    '消光': ['消光', 'matte', '哑光', '消光', '雾面'],
    '珠光': ['珠光', 'pearl', '珠光', '闪烁', '金属'],
    '增白': ['增白', 'white', '白度', '增白', '荧光', 'bright'],
    '抗粘': ['抗粘', 'anti-block', '防粘', '粘连', 'block', '开口', '滑'],
    '防粘结': ['防粘结', 'anti-block', '防粘', '粘连', 'block', '开口'],
    '相容': ['相容', 'compatibil', '接枝', '改性', '增容'],
    '着色': ['着色', 'color', '色母', '颜料', '染料', '色粉'],
    '开口': ['开口', 'slip', '爽滑', '抗粘', 'anti-block'],
}


def classify_by_text(text, title):
    """基于文本内容分类"""
    text_lower = text.lower()
    title_lower = title.lower()
    combined = text_lower + ' ' + title_lower

    material_types = []
    function_tags = []

    # 材料类型匹配
    for mat_type, keywords in MATERIAL_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in combined:
                if mat_type not in material_types:
                    material_types.append(mat_type)
                break

    # 功效标签匹配
    for func_type, keywords in FUNCTION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in combined:
                if func_type not in function_tags:
                    function_tags.append(func_type)
                break

    # 特殊规则：母料相关
    if '母料' in title or '母粒' in title or 'masterbatch' in title_lower:
        if '母料' not in material_types:
            material_types.append('母料')

    # 特殊规则：PP基材料
    if 'PP' in title or '聚丙烯' in title:
        if '热塑性' not in material_types:
            material_types.append('热塑性')
        if '通用塑料' not in material_types:
            material_types.append('通用塑料')

    # 特殊规则：TDS/技术资料
    if 'TDS' in title or '技术资料' in title or '物性' in title:
        if '功能材料' not in material_types:
            material_types.append('功能材料')

    # 特殊规则：检测报告
    if '检测' in title or '报告' in title or 'COA' in title:
        if '功能材料' not in material_types:
            material_types.append('功能材料')

    # 特殊规则： adhesives
    if 'adhesive' in title_lower or 'resin' in title_lower or '粘' in title:
        if '胶粘剂' not in material_types:
            material_types.append('胶粘剂')

    return material_types, function_tags


def main():
    docs = list_documents()
    print(f"共 {len(docs)} 份文档待分类")

    updated = 0
    for doc in docs:
        doc_id = doc['id']
        title = doc.get('title', '')
        content = doc.get('content_text', '')

        mat_types, func_tags = classify_by_text(content, title)

        # 如果没有识别到任何类型，给一个默认标签
        if not mat_types:
            mat_types = ['其他']
        if not func_tags:
            func_tags = ['其他']

        # 更新数据库
        update_document(doc_id,
                        material_types=mat_types,
                        function_tags=func_tags)

        print(f"[{doc_id}] {title[:50]}")
        print(f"    材料: {', '.join(mat_types)}")
        print(f"    功效: {', '.join(func_tags)}")
        updated += 1

    print(f"\n✅ 完成 {updated} 份文档的分类")


if __name__ == '__main__':
    main()
