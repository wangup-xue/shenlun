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
    # 主池：优先人民日报纸面版与人民日报系深度报道、评论。
    ('人民日报', 'site:paper.people.com.cn/rmrb (改革 OR 发展 OR 治理 OR 民生 OR 经济 OR 生态 OR 科技 OR 法治)'),
    ('人民日报', 'site:paper.people.com.cn (人民眼 OR 调查与思考 OR 人民锐评 OR 今日谈 OR 微观 OR 专题深思)'),
    ('人民日报', 'site:people.com.cn 人民日报 (高质量发展 OR 现代化 OR 基层治理 OR 民生 OR 绿色发展)'),
    ('人民日报', '人民日报 经济社会生态法治文化 深度报道 评论 2026'),
    # 补充池：江苏省级与13市实践，不与人民日报主池等量竞争。
    ('江苏省级', '江苏省 政府 工作部署 改革发展 民生 生态 科技'),
    ('南京', '南京 市政府 改革发展 民生 科技'),
    ('无锡', '无锡 市政府 太湖 生态 产业 创新'),
    ('徐州', '徐州 市政府 转型发展 产业 民生'),
    ('常州', '常州 新能源 先进制造 市政府'),
    ('苏州', '苏州 工业园区 营商环境 科技创新'),
    ('南通', '南通 跨江融合 沿海发展 市政府'),
    ('连云港', '连云港 港口 开放发展 市政府'),
    ('淮安', '淮安 洪泽湖 现代农业 市政府'),
    ('盐城', '盐城 黄海湿地 新能源 市政府'),
    ('扬州', '扬州 大运河 文化保护 市政府'),
    ('镇江', '镇江 长江岸线 生态修复 市政府'),
    ('泰州', '泰州 中国医药城 生物医药 市政府'),
    ('宿迁', '宿迁 农村电商 乡村振兴 市政府'),
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


# 申论相关性词：人民日报全国新闻需命中至少一项，避免国际快讯、社会琐闻挤占素材位。
NATIONAL_RELEVANCE = [
    "改革", "发展", "治理", "民生", "高质量", "现代化", "创新", "科技", "人工智能",
    "产业", "制造", "新能源", "绿色", "生态", "环保", "乡村", "农业", "粮食",
    "教育", "就业", "医疗", "养老", "社会保障", "公共服务", "营商环境", "市场监管",
    "法治", "基层", "社区", "文化", "非遗", "文旅", "文化遗产", "数字经济",
    "共同富裕", "区域协调", "城乡", "开放", "国际合作", "气候", "减污", "双碳",
    "知识产权", "人才", "创业", "消费", "提振", "安全生产", "应急管理", "社会治理",
    "国企", "民营经济", "长三角", "长江经济带", "黄河", "大运河", "公共卫生"
]
IRRELEVANT_MARKERS = [
    "枪击", "交火", "死亡人数", "致死", "遇难", "车祸", "交通事故", "楼房倒塌",
    "炸弹威胁", "被捕", "犯罪嫌疑人", "球赛", "夺冠", "比分", "明星", "演唱会",
    "换牙", "就医提醒", "股价", "国际油价", "特朗普发帖", "选举民调"
]
def is_relevant(item):
    title = item.get("title", "")
    text = title + " " + item.get("summary", "")
    category = item.get("category", "")
    if any(word in text for word in IRRELEVANT_MARKERS):
        return False
    # 人民日报国际版突发/外交快讯不作为江苏申论日常素材主池。
    # 江苏城市对外交流类报道仍按城市分类保留。
    if category == "人民日报" and ("--国际" in title or "国际 - 人民网" in title):
        return False
    if category == "人民日报":
        return any(word in text for word in NATIONAL_RELEVANCE)
    if category == "江苏省级":
        return "江苏" in text
    if category in ("南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁"):
        return category in text or "江苏" + category in text
    return False

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
                if is_relevant(item):
                    old[item['url']] = item
        except Exception as exc:
            errors.append(f'{label}: {exc}')
    candidates = [x for x in old.values() if is_relevant(x)]
    # 主池与补充池分开排序：最多300条时优先保证约70%人民日报内容；
    # 若人民日报当期供稿不足，再由江苏省级及13市真实报道补位，不伪造条目。
    national = sorted((x for x in candidates if x.get('category') == '人民日报'),
                      key=lambda x: (x.get('date',''), x.get('title','')), reverse=True)
    local = sorted((x for x in candidates if x.get('category') != '人民日报'),
                   key=lambda x: (x.get('date',''), x.get('title','')), reverse=True)
    cap = 300
    national_quota = 210
    local_quota = cap - national_quota
    items = national[:national_quota] + local[:local_quota]
    if len(items) < cap:
        remaining = national[national_quota:] + local[local_quota:]
        items.extend(remaining[:cap-len(items)])
    payload = {'updated': datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S'),
               'timezone': 'Asia/Shanghai', 'items': items, 'warnings': errors,
               'source_policy': {'primary': '人民日报及人民日报系评论、深度报道', 'supplementary': '江苏省级及13个设区市真实报道', 'target_mix': '最多300条时优先约70%人民日报、约30%江苏地方；人民日报不足时由地方报道补位'},
               'notice': '人民日报为主池，江苏省级及13市为补充池。RSS仅用于新闻发现；请打开原文核验来源、事实和数据。本站不转载新闻全文。'}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f'已保存 {len(items)} 条新闻元数据；RSS源异常 {len(errors)} 个')

if __name__ == '__main__':
    main()
