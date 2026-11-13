# -*- coding: utf-8 -*-
"""江苏新闻申论线索卡片。仅分析RSS标题/短摘要，不抓取或保存新闻全文。"""
# SiliconFlow API credentials are supplied through GitHub Actions Secrets; never store keys in source.
# Retest marker: verify current SiliconFlow account balance and live inference.
import json
import os
import re
import sys
import urllib.request
import urllib.error
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
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import annotate
    provider = os.environ.get("LLM_PROVIDER", "siliconflow").strip().lower()
    if provider not in ("siliconflow", "minimax"):
        raise SystemExit("LLM_PROVIDER 仅支持 siliconflow 或 minimax")
    if provider == "siliconflow":
        api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
        api_base = (os.environ.get("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1").strip().rstrip("/")
        model = (os.environ.get("SILICONFLOW_MODEL") or "deepseek-ai/DeepSeek-V3.2").strip()
    else:
        api_key = annotate.read_api_key()
        api_base = ""
        model = "MiniMax-M3.1-Flash"
    has_key = bool(api_key)

    def call_provider(prompt, max_tokens=1200):
        if provider == "minimax":
            return annotate.call_llm(prompt, max_tokens=max_tokens)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2
        }
        request = urllib.request.Request(
            api_base + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:500]
            raise RuntimeError("SiliconFlow HTTP %s: %s" % (exc.code, detail)) from exc
        except Exception as exc:
            raise RuntimeError("SiliconFlow 请求失败: %s" % exc) from exc
        choices = result.get("choices") or []
        if not choices:
            raise RuntimeError("SiliconFlow 未返回 choices: " + str(result)[:300])
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not str(content).strip():
            content = message.get("reasoning_content", "")
        if not str(content).strip():
            raise RuntimeError("SiliconFlow 返回内容为空")
        return str(content)
    # 分层选材：先覆盖13市，再选省级报道，最后补充人民日报全国性议题。
    city_items = {city: [] for city in CITY_NAMES}
    provincial_items, national_items = [], []
    for row in items:
        cat = row.get("category", "")
        if cat in city_items:
            city_items[cat].append(row)
        elif cat == "江苏省级":
            provincial_items.append(row)
        elif cat == "人民日报":
            national_items.append(row)
    selected, used = [], set()
    # 每市最多先取2条，按城市轮转，避免单一城市占满首页。
    for round_index in range(2):
        for city in CITY_NAMES:
            for row in city_items[city][round_index:round_index + 1]:
                if row.get("url") not in used:
                    selected.append(row); used.add(row.get("url"))
    for pool, cap in ((provincial_items, 7), (national_items, 30)):
        added = 0
        for row in pool:
            if row.get("url") not in used and len(selected) < 30 and added < cap:
                selected.append(row); used.add(row.get("url")); added += 1
    # 城市新闻不足时，用全国性报道补足，不重复。
    for row in items:
        if len(selected) >= 30:
            break
        if row.get("url") not in used:
            selected.append(row); used.add(row.get("url"))
    leads = []
    for item in selected[:30]:
        city = city_for(item)
        card = fallback(item, city)
        if has_key and annotate:
            prompt = (
                "你是江苏省考申论教研员。只根据给出的新闻标题和RSS短摘要做谨慎的摘要级研判，"
                "不得补造新闻事实、数字、政策名称或直接引语。输出纯JSON，字段："
                "topic（主题）、thesis（申论总论点）、policy_angles（2-3条可迁移分析角度）、"
                "three_color_notes（对象含论点、金句提炼、案例；金句提炼必须明确是概括而非原文引语）、"
                "evidence_warning（提醒打开原文核验）。如信息不足请明确写待核。"
                "\n城市归属：" + city
                + "\n标题：" + item.get("title", "")
                + "\nRSS摘要：" + item.get("summary", "")
            )
            try:
                data = annotate.extract_json(call_provider(prompt, max_tokens=1200))
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
        "provider": provider,
        "model": model if provider == "siliconflow" else "MiniMax-M3.1-Flash",
        "items": leads
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("已生成 %d 条江苏申论线索卡片；AI密钥%s（服务商：%s）" % (len(leads), "已配置" if has_key else "未配置，使用待分析模板", provider))

if __name__ == "__main__":
    main()
