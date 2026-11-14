# -*- coding: utf-8 -*-
"""人民日报原文研读：解析RSS跳转、提取正文并只保存自主分析，不保存全文。"""
import json, os, re, sys, urllib.request, urllib.error
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "jiangsu")
CST = timezone(timedelta(hours=8))
MAX_ARTICLE_CHARS = 18000
MIN_BODY_CHARS = 700
GOOGLE_HOSTS = ("news.google.com", "google.com", "www.google.com")
PUBLISHER_HOSTS = ("paper.people.com.cn", "people.com.cn", "人民网")

class TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}
    MARKERS = ("article", "content", "text", "正文", "rm_txt", "ozoom", "detail", "main")
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.candidate_depth = 0
        self.all_parts, self.candidate_parts = [], []
        self.candidate_lengths = []
        self.tag_stack = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP: self.skip += 1
        cls = (attrs.get("class", "") + " " + attrs.get("id", "")).lower()
        is_candidate = tag == "article" or (tag in ("div", "section", "main") and any(m in cls for m in self.MARKERS))
        self.tag_stack.append((tag, is_candidate))
        if is_candidate:
            self.candidate_depth += 1
            self.candidate_lengths.append(len(self.candidate_parts))
        if tag in ("p", "div", "section", "h1", "h2", "h3", "li", "br"):
            self.all_parts.append("\n")
            if self.candidate_depth: self.candidate_parts.append("\n")
    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip: self.skip -= 1
        for i in range(len(self.tag_stack) - 1, -1, -1):
            if self.tag_stack[i][0] == tag:
                popped = self.tag_stack[i:]
                self.tag_stack = self.tag_stack[:i]
                self.candidate_depth = max(0, self.candidate_depth - sum(1 for _, flag in popped if flag))
                break
        if tag in ("p", "div", "section", "h1", "h2", "h3", "li"):
            self.all_parts.append("\n")
            if self.candidate_depth: self.candidate_parts.append("\n")
    def handle_data(self, data):
        if self.skip or not data.strip(): return
        value = data.strip()
        self.all_parts.append(value)
        if self.candidate_depth: self.candidate_parts.append(value)

def clean_text(parts):
    text = re.sub(r"[ \t\r]+", " ", "\n".join(parts))
    lines = [x.strip() for x in re.split(r"\n+", text) if len(x.strip()) >= 8]
    # 去除常见导航/版权/页面操作噪声
    noise = ("字体：", "打印", "分享", "客户端", "人民日报社概况", "京ICP备", "版权所有", "广告", "返回顶部")
    lines = [x for x in lines if not any(n in x for n in noise)]
    return "\n".join(lines)

def request_page(url, limit=3000000):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=35) as resp:
        final = resp.geturl()
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read(limit)
    return final, ctype, raw

def resolve_google_link(url):
    host = (urlparse(url).hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in GOOGLE_HOSTS):
        return url
    final, ctype, raw = request_page(url, 1800000)
    if not any((urlparse(final).hostname or "").lower().endswith(h) for h in GOOGLE_HOSTS):
        return final
    html = raw.decode("utf-8", "ignore")
    candidates = []
    patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:og:url|twitter:url)["\'][^>]+content=["\']([^"\']+)',
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:url|twitter:url)',
        r'<a[^>]+href=["\'](https?://[^"\']+)["\']',
    ]
    for pattern in patterns:
        for value in re.findall(pattern, html, re.I):
            value = value.replace("&amp;", "&")
            absolute = urljoin(final, value)
            h = (urlparse(absolute).hostname or "").lower()
            if any(h == x or h.endswith("." + x) for x in ("people.com.cn", "paper.people.com.cn")):
                candidates.append(absolute)
    # Prefer article-level URLs over publisher homepages and Google tracking links.
    for value in candidates:
        path = urlparse(value).path
        if len(path.strip("/")) > 12 and not path.endswith((".jpg", ".png")):
            return value
    raise RuntimeError("Google News跳转页未解析出人民日报/人民网原文地址")

def extract_body(html):
    parser = TextParser()
    parser.feed(html)
    candidate = clean_text(parser.candidate_parts)
    full = clean_text(parser.all_parts)
    # 正文容器优先；否则只接受足够长且有段落结构的页面文本
    body = candidate if len(candidate) >= MIN_BODY_CHARS else full
    if len(body) < MIN_BODY_CHARS:
        raise RuntimeError("页面正文不足700字，可能是跳转页、验证码或页面框架")
    return body[:MAX_ARTICLE_CHARS]

def fetch_article(url):
    resolved = resolve_google_link(url)
    final, ctype, raw = request_page(resolved)
    host = (urlparse(final).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in GOOGLE_HOSTS):
        raise RuntimeError("最终地址仍为Google News跳转页")
    if "pdf" in ctype.lower() or final.lower().endswith(".pdf"):
        raise RuntimeError("原文为PDF，当前自动正文提取器暂不支持PDF")
    if "html" not in ctype.lower() and b"<html" not in raw[:1000].lower():
        raise RuntimeError("原文返回的不是HTML页面")
    return final, extract_body(raw.decode("utf-8", "ignore"))

def call_model(prompt):
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key: raise RuntimeError("未配置SILICONFLOW_API_KEY")
    base = (os.environ.get("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1").rstrip("/")
    model = os.environ.get("SILICONFLOW_MODEL") or "deepseek-ai/DeepSeek-V3.2"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 3000, "temperature": 0.12}
    req = urllib.request.Request(base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("硅基流动HTTP %s: %s" % (exc.code, exc.read().decode("utf-8", "ignore")[:240]))
    choices = data.get("choices") or []
    if not choices: raise RuntimeError("模型未返回choices")
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)

def parse_json(text):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from annotate import extract_json
    return extract_json(text)

def is_people_daily(row):
    label = (row.get("category", "") + " " + row.get("source", "")).lower()
    return "人民日报" in label or "人民网" in label

def main():
    path = os.path.join(DATA, "leads.json")
    with open(path, encoding="utf-8") as f: payload = json.load(f)
    items = payload.get("items", [])
    counts = {"success": 0, "unavailable": 0, "failed": 0, "skipped": 0}
    errors = []
    for row in items:
        if not is_people_daily(row):
            counts["skipped"] += 1
            continue
        analysis = row.setdefault("analysis", {})
        if analysis.get("reading_status") == "full_text_read":
            counts["skipped"] += 1
            continue
        try:
            final_url, body = fetch_article(row.get("url", ""))
            prompt = (
                "你是人民日报原文研读型申论教研员。只依据下面可读取的文章正文，充分提取事实并用自己的语言组织分析。"
                "严禁补造事实、数据、人物、政策和引语。只输出JSON，不要代码围栏。字段：topic、thesis（80-150字）、"
                "policy_angles（3-5条）、three_color_notes（论点、金句提炼、案例；金句提炼必须注明‘申论概括表达，非原文引语’）、"
                "argument_expansion（4-6条具体分论点和论证逻辑）、key_facts（最多8条，保留主体、地点、时间、做法、结果和数字口径）、"
                "writing_application、evidence_warning（地域、时间、统计口径和适用边界）。"
                "不能把全国数据写成江苏数据；正文未给出的事实不得推测。"
                "\n标题：" + row.get("title", "") + "\n来源：" + row.get("source", "") +
                "；日期：" + row.get("date", "") + "\n原文链接：" + final_url +
                "\n以下正文仅用于分析，不要复述全文：\n" + body
            )
            result = parse_json(call_model(prompt))
            required = ("topic", "thesis", "policy_angles", "three_color_notes", "argument_expansion",
                        "key_facts", "writing_application", "evidence_warning")
            missing = [k for k in required if k not in result]
            if missing: raise RuntimeError("模型分析缺少字段：" + ",".join(missing))
            if len(str(result.get("thesis", ""))) < 50 or not result.get("key_facts"):
                raise RuntimeError("模型分析内容不足，缺少有效论点或关键事实")
            analysis.update(result)
            analysis["level"] = "原文全文研读"
            analysis["reading_status"] = "full_text_read"
            analysis["source_url"] = final_url
            analysis["source_body_chars"] = len(body)
            analysis["evidence_warning"] = str(analysis.get("evidence_warning", "")) + " 本卡基于已读取正文生成；网站仅保存自主分析，不保存新闻全文。"
            counts["success"] += 1
        except Exception as exc:
            message = str(exc)[:220]
            analysis["level"] = "原文待核（自动读取未成功）"
            analysis["reading_status"] = "unavailable"
            analysis["reading_error"] = message
            errors.append({"title": row.get("title", ""), "reason": message})
            counts["unavailable"] += 1
    payload["updated"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    payload["fulltext_reading_report"] = {
        "updated": payload["updated"], "success": counts["success"],
        "unavailable": counts["unavailable"], "skipped": counts["skipped"],
        "method": "解析Google News跳转链接后读取发布方原文；正文不足700字或缺少关键事实均不计成功",
        "errors": errors[:30]
    }
    payload["analysis_mode"] = "人民日报原文优先研读；只有正文提取、模型分析和关键事实校验均通过才标记全文研读。"
    payload["fulltext_policy"] = "原文仅在运行时用于分析，不保存或发布新闻全文；公开内容为自主总结、事实摘录、申论归纳及原文链接。"
    with open(path, "w", encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False, indent=2)
    print("人民日报原文研读报告：" + json.dumps(payload["fulltext_reading_report"], ensure_ascii=False))
    if counts["success"] == 0 and counts["unavailable"] > 0:
        print("::warning::本轮未成功读取任何原文；不得将工作流绿色状态理解为全文研读成功。")

if __name__ == "__main__":
    main()
