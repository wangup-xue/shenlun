# -*- coding: utf-8 -*-
"""读取新闻原文供模型研读；仅保存自主分析，不保存或发布新闻全文。"""
import json
import os
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "jiangsu")
CST = timezone(timedelta(hours=8))
MAX_ARTICLE_CHARS = 14000
SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}

class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip_depth, self.article_depth = [], 0, 0
        self.in_article = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        if tag == "article":
            self.in_article = True
            self.article_depth += 1
        cls = (attrs.get("class", "") + " " + attrs.get("id", "")).lower()
        if any(x in cls for x in ("article-content", "articlecontent", "rm_txt", "text_con", "content-main")):
            self.in_article = True
        if tag in ("p", "div", "h1", "h2", "h3", "br", "li"):
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag == "article" and self.article_depth:
            self.article_depth -= 1
            if not self.article_depth:
                self.in_article = False
        if tag in ("p", "div", "h1", "h2", "h3", "li"):
            self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip_depth and data.strip():
            self.parts.append(data.strip())

def fetch_article(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; JiangsuShenlun/1.0)", "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        final_url = resp.geturl()
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype.lower():
            return final_url, ""
        raw = resp.read(2_500_000).decode("utf-8", "ignore")
    parser = ArticleParser()
    parser.feed(raw)
    text = re.sub(r"[ \t\r]+", " ", "\n".join(parser.parts))
    text = re.sub(r"\n{2,}", "\n", text)
    # 过滤明显的站点导航、版权尾注和过短噪声
    lines = [x.strip() for x in text.splitlines() if len(x.strip()) >= 8]
    body = "\n".join(lines)
    return final_url, body[:MAX_ARTICLE_CHARS]

def call_model(prompt):
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key:
        raise RuntimeError("未配置 SILICONFLOW_API_KEY")
    base = (os.environ.get("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1").rstrip("/")
    model = os.environ.get("SILICONFLOW_MODEL") or "deepseek-ai/DeepSeek-V3.2"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 2600, "temperature": 0.15}
    req = urllib.request.Request(base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("模型接口HTTP %s: %s" % (exc.code, exc.read().decode("utf-8", "ignore")[:250]))
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("模型未返回内容")
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)

def main():
    path = os.path.join(DATA, "leads.json")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    items = payload.get("items", [])
    processed, failures = 0, 0
    for row in items:
        analysis = row.setdefault("analysis", {})
        if analysis.get("level") in ("人民日报原文内容提炼", "原文核验型申论素材"):
            continue
        if row.get("category") != "人民日报":
            continue
        try:
            final_url, body = fetch_article(row.get("url", ""))
            if len(body) < 500:
                analysis["level"] = "原文待核（页面不可读取或正文不足）"
                analysis["reading_status"] = "unavailable"
                analysis["evidence_warning"] = "未能从原文页面提取足够正文；本卡不得视为全文研读，现有内容仅供线索参考。"
                failures += 1
                continue
            prompt = (
                "你是人民日报原文研读型申论教研员。下面给出一篇新闻报道/评论的可读取正文。"
                "请仅依据正文，充分提取事实并用自己的语言组织申论分析。严禁补造事实、数据、人物、政策和引语。"
                "输出一个JSON对象，不要代码围栏，字段为：topic、thesis（80-150字）、policy_angles（3-5条）、"
                "three_color_notes（论点、金句提炼、案例；金句提炼必须标注‘申论概括表达，非原文引语’）、"
                "argument_expansion（4-6条，每条为具体分论点及论证逻辑）、"
                "key_facts（最多8条，保留主体、地点、时间、做法、结果和原文数字口径）、"
                "writing_application（适用主题和写作结构）、evidence_warning（地域、时间、统计口径和适用边界）。"
                "论点展开要有内容，案例尽量保留正文中的具体事实，不得把全国数据写成江苏数据。"
                "\n标题：" + row.get("title", "") +
                "\n来源：" + row.get("source", "") + "；日期：" + row.get("date", "") +
                "\n原文链接：" + final_url + "\n正文（仅用于本次分析，不要复述全文）：\n" + body
            )
            import sys
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            from annotate import extract_json
            result = extract_json(call_model(prompt))
            analysis.update(result)
            analysis["level"] = "原文全文研读"
            analysis["reading_status"] = "full_text_read"
            analysis["source_url"] = final_url
            analysis["evidence_warning"] = str(analysis.get("evidence_warning", "")) + " 本卡基于本次可读取正文生成；网站仅保存分析摘要，不保存新闻全文。"
            processed += 1
        except Exception as exc:
            analysis["level"] = "原文读取/分析失败（保留摘要级）"
            analysis["reading_status"] = "failed"
            analysis["reading_error"] = str(exc)[:220]
            failures += 1
    payload["updated"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    payload["analysis_mode"] = "人民日报原文优先研读；成功读取标记原文全文研读，失败明确标注；地方及未读取内容保留原级别"
    payload["fulltext_policy"] = "原文仅在运行时用于分析，不保存或发布全文；公开内容为自主总结、事实摘录、申论归纳及原文链接。"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("人民日报原文研读完成：成功 %d 条，未成功 %d 条；未保存新闻全文。" % (processed, failures))

if __name__ == "__main__":
    main()
