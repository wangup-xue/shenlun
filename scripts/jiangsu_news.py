# -*- coding: utf-8 -*-
"""通过 RSS 发现人民日报及江苏政务新闻；只保存元数据和短摘要，不镜像全文。"""
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "jiangsu", "news.json")
CST = timezone(timedelta(hours=8))
QUERIES = [
    ('人民日报', 'site:people.com.cn (人民日报 OR 人民日报评论)'),
    ('江苏', '江苏 省政府 改革发展 民生 生态 科技'),
    ('南京', '南京 市政府 发展 民生 科技'),
    ('苏州', '苏州 市政府 产业 创新 营商环境'),
    ('无锡常州', '无锡 OR 常州 产业 生态 新能源'),
    ('江苏其他设区市', '江苏 徐州 南通 连云港 淮安 盐城 扬州 镇江 泰州 宿迁 政务 发展'),
]

def clean(value):
    return re.sub(r'\s+', ' ', value or '').strip()

def fetch(query, label):
    params = urllib.parse.urlencode({'q': query, 'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans'})
    url = 'https://news.google.com/rss/search?' + params
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; JiangsuShenlun/1.0)'})
    with urllib.request.urlopen(req, timeout=25) as resp:
        root = ET.fromstring(resp.read())
    rows = []
    for item in root.findall('./channel/item'):
        title = clean(item.findtext('title'))
        link = clean(item.findtext('link'))
        source = clean(item.find('source').text if item.find('source') is not None else label)
        desc = clean(item.findtext('description'))
        desc = clean(re.sub(r'<[^>]+>', ' ', desc))[:240]
        pub = clean(item.findtext('pubDate'))
        try:
            dt = parsedate_to_datetime(pub).astimezone(CST).strftime('%Y-%m-%d')
        except Exception:
            dt = ''
        if title and link:
            rows.append({'title': title, 'source': source, 'date': dt, 'url': link,
                         'summary': desc, 'category': label})
    return rows

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    old = {}
    try:
        with open(OUT, encoding='utf-8') as f:
            old = {x.get('url'): x for x in json.load(f).get('items', []) if x.get('url')}
    except Exception:
        pass
    errors = []
    for label, query in QUERIES:
        try:
            for item in fetch(query, label):
                old[item['url']] = item
        except Exception as exc:
            errors.append(f'{label}: {exc}')
    items = sorted(old.values(), key=lambda x: (x.get('date',''), x.get('title','')), reverse=True)[:300]
    payload = {'updated': datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S'),
               'timezone': 'Asia/Shanghai', 'items': items, 'warnings': errors,
               'notice': 'RSS仅用于新闻发现；请打开原文核验来源、事实和数据。本站不转载新闻全文。'}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f'已保存 {len(items)} 条新闻元数据；RSS源异常 {len(errors)} 个')

if __name__ == '__main__':
    main()
