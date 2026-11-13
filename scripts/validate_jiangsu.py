# -*- coding: utf-8 -*-
"""对江苏版数据结构做无网络、无密钥的发布前校验。"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "jiangsu")
EXPECTED_CITIES = ["南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁"]

def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)

def main():
    cases = load("cases.json")
    cities = cases.get("cities", [])
    names = [x.get("city") for x in cities]
    assert len(names) == 13, f"案例城市应为13个，实际{len(names)}"
    assert len(set(names)) == 13, "案例城市存在重复"
    assert set(names) == set(EXPECTED_CITIES), "案例城市未完整覆盖江苏13市"
    for row in cities:
        assert row.get("case") and row.get("topic") and row.get("angles"), f"案例字段不完整：{row}"
        assert re.match(r"^https?://", row.get("url", "")), f"官网链接无效：{row.get('city')}"
    terms = load("terms.json")
    entries = terms.get("terms", [])
    assert len(entries) >= 20, "江苏表达词库条目不足20条"
    seen = set()
    for row in entries:
        for key in ("term", "definition", "usage", "theme", "source_type", "verification_note"):
            assert row.get(key), f"词条缺少{key}字段：{row}"
        assert row["term"] not in seen, f"词条重复：{row['term']}"
        seen.add(row["term"])
        assert row["source_type"] == "通用写作表达", f"词条误标为官方术语：{row['term']}"
    for filename in ("news.json", "leads.json"):
        payload = load(filename)
        assert isinstance(payload.get("items"), list), f"{filename} 的 items 必须为数组"
    print(f"江苏版数据校验通过：13市案例、{len(entries)}条原创通用表达、新闻与线索数据结构正常")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("江苏版数据校验失败：", exc, file=sys.stderr)
        raise
