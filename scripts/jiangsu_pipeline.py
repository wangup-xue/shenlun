# -*- coding: utf-8 -*-
"""江苏新闻申论线索卡片。仅分析RSS标题/短摘要，不抓取或保存新闻全文。"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "jiangsu")
CST = timezone(timedelta(hours=8))
CITY_NAMES = ["南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁"]
TOPIC_HINTS = {
    "生态治理": ["生态", "湿地", "太湖", "长江", "污染", "绿色", "环保"],
    "科技创新": ["科技", "创新", "实验室", "人工智能", "研发", "人才"],
    "产业发展": ["产业", "制造", "新能源", "企业", "工业", "经济"],
    "基层治理": ["基层", "治理", "社区", "公共服务", "民生"],
    "乡村振兴": ["乡村", "农业", "农村", "粮食", "电商"],
    "改革开放": ["改革", "开放", "营商环境", "园区", "港口", "物流"],
    "文化传承": ["文化", "大运河", "文旅", "遗产", "非遗"],
}

def city_for(item):
    cat = item.get("category", "")
    if cat in CITY_NAMES:
        return cat
    title = (item.get("title", "") + " " + item.get("summary", ""))
    hits = [c for c in CITY_NAMES if c in title]
    return hits[0] if len(hits) == 1 else ("江苏全省" if cat == "江苏省级" else "全国/待核")

def topic_for(text):
    for topic, words in TOPIC_HINTS.items():
        if any(w in text for w in words):
            return topic
    return "综合治理与高质量发展"

def fallback(item, city):
    text = (item.get("title", "") + " " + item.get("summary", "")).strip()
    topic = topic_for(text)
    return {
        "level": "待AI分析",
        "topic": topic,
        "thesis": "围绕" + topic + "，统筹目标引领、问题破解与长效机制建设。",
        "policy_angles": ["坚持问题导向，找准制约发展的关键堵点", "强化系统施策，推动资源、政策与主体协同发力"],
        "three_color_notes": {
            "论点": "可从" + topic + "的现实意义、突出问题和治理路径展开。",
            "金句提炼": "摘要未提供可核验原句；此处为写作思路，不是新闻引语。",
            "案例": "关注" + city + "相关实践；具体做法、数字和成效须打开原文核验。"
        },
        "evidence_warning": "当前仅有RSS标题/短摘要，尚未进行全文核验；不得将推演内容当作新闻事实。"
    }

def main():
    os.makedirs(DATA, exist_ok=True)
    news_path = os.path.join(DATA, "news.json")
    out_path = os.path.join(DATA, "leads.json")
    try:
        with open(news_path, encoding="utf-8") as f:
            news = json.load(f)
    except Exception as exc:
        raise SystemExit("新闻元数据不可用: " + str(exc))
    items = news.get("items", [])
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import annotate
        has_key = bool(annotate.read_api_key())
    except Exception:
        annotate = None
        has_key = False
    leads = []
    for item in items[:30]:
        city = city_for(item)
        card = fallback(item, city)
        if has_key and annotate:
            prompt = (
                "你是江苏省考申论教研员。只根据给出的新闻标题和RSS短摘要做谨慎的摘要级研判，"
                "不得补造新闻事实、数字、政策名称或直接引语。输出纯JSON，字段："
                "topic（主题）、thesis（申论总论点）、policy_angles（2-3条可迁移分析角度）、"
                "three_color_notes（对象含论点、金句提炼、案例；金句提炼必须明确是概括而非原文引语）、"
                "evidence_warning（提醒打开原文核验）。如信息不足请明确写待核。"
                "\\n城市归属：" + city
                + "\\n标题：" + item.get("title", "")
                + "\\nRSS摘要：" + item.get("summary", "")
            )
            try:
                data = annotate.extract_json(annotate.call_llm(prompt, max_tokens=1200))
                card.update(data)
                card["level"] = "RSS摘要级AI分析"
            except Exception as exc:
                card["level"] = "AI分析暂不可用"
                card["analysis_error"] = str(exc)[:180]
        leads.append({
            "title": item.get("title", ""), "source": item.get("source", ""),
            "date": item.get("date", ""), "url": item.get("url", ""),
            "category": item.get("category", ""), "city": city,
            "summary": item.get("summary", ""), "analysis": card
        })
    payload = {
        "updated": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Asia/Shanghai",
        "analysis_mode": "RSS标题与短摘要级；不是全文分析",
        "items": leads
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("已生成 %d 条江苏申论线索卡片；AI密钥%s" % (len(leads), "已配置" if has_key else "未配置，使用待分析模板"))

if __name__ == "__main__":
    main()
