import feedparser
import json
import os
import requests
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

RSS_FEEDS = [
    {"url": "http://feeds.bbci.co.uk/news/business/rss.xml",                                                              "source": "BBC",      "cat": "economy"},
    {"url": "http://feeds.bbci.co.uk/news/technology/rss.xml",                                                            "source": "BBC",      "cat": "tech"},
    {"url": "http://feeds.bbci.co.uk/news/world/rss.xml",                                                                 "source": "BBC",      "cat": "politics"},
    {"url": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",                                               "source": "BBC",      "cat": "tech"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",                       "source": "CNBC",     "cat": "finance"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",                        "source": "CNBC",     "cat": "tech"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",                        "source": "CNBC",     "cat": "finance"},
    {"url": "https://news.google.com/rss/search?q=when:48h+allinurl:bloomberg.com&ceid=US:en&hl=en-US&gl=US",            "source": "Bloomberg","cat": "finance"},
    {"url": "https://news.google.com/rss/search?q=when:48h+allinurl:bloomberg.com+technology&ceid=US:en&hl=en-US&gl=US", "source": "Bloomberg","cat": "tech"},
]

MAX_PER_SOURCE = 10
KEEP_HOURS = 48

INVALID_TITLES = {
    '标题', '标题：', '标题:', '题目', '无', '无标题',
    'n/a', 'none', 'null', '/', '-', '', 'title', 'headline'
}


def parse_published(published_str):
    try:
        return parsedate_to_datetime(published_str).astimezone(timezone.utc)
    except:
        return None


def get_time_ago(dt):
    if not dt:
        return "今天"
    now = datetime.now(timezone.utc)
    diff = now - dt
    hours = int(diff.total_seconds() / 3600)
    if hours < 1:
        return "刚刚"
    elif hours < 24:
        return f"{hours}小时前"
    else:
        days = hours // 24
        return f"{days}天前"


def clean_title(raw):
    t = raw.strip()
    t = t.strip('[]【】「」《》')
    for prefix in ['标题：', '标题:', '第一行：', '第一行:', '中文标题：',
                   '中文标题:', '一、', '1. ', '1、', 'Title:', 'title:',
                   '**', '*']:
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    t = t.strip('*').strip()
    if '：' in t and len(t) < 20:
        t = t.split('：', 1)[-1].strip()
    if len(t) > 30:
        return ""
    if t.lower() in INVALID_TITLES or len(t) < 3:
        return ""
    return t


def clean_deck(text):
    """清除摘要中可能残留的前缀废话"""
    if not text:
        return ""
    prefixes = [
        '摘要：', '摘要:', '中文摘要：', '中文摘要:', '内容：', '内容:',
        '翻译：', '翻译:', '第二行：', '第二行:', '直译：', '直译:',
        '原文：', '原文:', '正文：', '正文:',
    ]
    for p in prefixes:
        if text.startswith(p):
            text = text[len(p):].strip()
    return text.strip()


def generate_cn_content(headline, deck):
    api_key = os.environ.get("AIOGE", "")
    if not api_key:
        return "SKIP", "", ""
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{
                        "text": (
                            f"判断以下新闻是否值得关注。\n"
                            f"只保留：重大地缘政治事件、全球金融市场动态、科技巨头重要动态、央行货币政策、重大经济数据、战争冲突、重要人物言论。\n"
                            f"不要：本地小事、娱乐体育、消费提示、交通延误、地方政策、动物故事、软性生活内容。\n\n"
                            f"如果不值得关注，只回复：SKIP\n\n"
                            f"如果值得关注，严格按以下格式输出，共三行，行与行之间只有换行符，"
                            f"每行【不加任何前缀、标签、序号、冒号、星号、markdown符号】，直接输出纯文本内容：\n"
                            f"第1行：中文标题，必须是简洁的新闻标题，8-15字，概括核心事件，不能是翻译腔，直接写标题文字\n"
                            f"第2行：中文摘要，将原文扩展翻译成中文，保留所有数字/人名/机构名/直接引语，字数必须在600到800字之间，内容完整充实，直接写摘要文字\n"
                            f"第3行：分类，只能是 economy 或 tech 或 finance 或 politics 四个词之一\n\n"
                            f"分类说明：economy=宏观经济/央行/贸易/通胀，tech=科技/AI/芯片/互联网，"
                            f"finance=金融市场/股票/外汇/加密/银行，politics=地缘政治/战争/选举/外交\n\n"
                            f"示例输出（注意：没有任何前缀标签，没有星号，没有markdown）：\n"
                            f"美联储维持利率不变\n"
                            f"美联储周三宣布维持联邦基金利率目标区间在5.25%至5.5%不变，符合市场普遍预期。美联储主席杰罗姆·鲍威尔在新闻发布会上表示，委员会在评估更多数据之前不会急于调整政策立场。鲍威尔强调，在通胀明确且持续回落至2%目标之前，委员会不会考虑降息。他同时指出，劳动力市场依然强劲，失业率维持在历史低位附近，消费支出保持韧性。市场参与者对此次决议反应平淡，此前已有充分预期。分析人士认为，美联储的谨慎态度反映出其对通胀粘性的担忧，尤其是核心通胀仍高于目标水平。部分联储官员在会后发言中暗示，年内降息次数可能少于市场预期，这一表态引发债券市场小幅波动，10年期美债收益率短暂走高后回落。\n"
                            f"economy\n\n"
                            f"新闻标题：{headline}\n"
                            f"新闻内容：{deck}"
                        )
                    }]
                }],
                "generationConfig": {"maxOutputTokens": 3000}
            },
            timeout=30
        )
        data = response.json()
        if "candidates" not in data:
            print(f"  API bad response: {data}")
            return "", "", ""
        content = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        if "SKIP" in content.upper() or "不值得" in content or "无需关注" in content or len(content) < 5:
            return "SKIP", "", ""

        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if len(lines) < 1:
            return "SKIP", "", ""

        cn_title = clean_title(lines[0])
        if not cn_title:
            print(f"  Invalid title after cleaning: '{lines[0]}', skipping")
            return "SKIP", "", ""

        cn_deck = clean_deck(lines[1]) if len(lines) > 1 else ""
        ai_cat  = lines[2].lower() if len(lines) > 2 else ""

        for prefix in ['分类：', '分类:', '第三行：', 'category:', 'Category:']:
            ai_cat = ai_cat.replace(prefix, '').strip()
        if ai_cat not in ('economy', 'tech', 'finance', 'politics'):
            ai_cat = ""

        print(f"  ✅ '{cn_title[:25]}' | cat={ai_cat}")
        return cn_title, cn_deck, ai_cat

    except Exception as e:
        print(f"  API error: {e}")
        return "", "", ""
    finally:
        time.sleep(13)  # 每分钟限5次，间隔13秒确保不超限


def fetch_news():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=KEEP_HOURS)

    existing = []
    existing_urls = set()
    try:
        with open("data/news.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing = [
            item for item in existing
            if item.get("published_iso") and
               datetime.fromisoformat(item["published_iso"]) >= cutoff
        ]
        for item in existing:
            item.pop("is_new", None)
        existing_urls = {item["url"] for item in existing}
        print(f"Loaded {len(existing)} existing items within 48h")
    except Exception as e:
        print(f"No existing news.json or parse error: {e}")

    source_candidates = {}
    seen_urls = set(existing_urls)
    seen_titles = set()

    for feed_info in RSS_FEEDS:
        source = feed_info["source"]
        if source not in source_candidates:
            source_candidates[source] = []
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:20]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                if not title or not link:
                    continue
                if link in seen_urls or title in seen_titles:
                    continue
                published_str = entry.get("published", "")
                dt = parse_published(published_str)
                if dt and dt < cutoff:
                    continue
                seen_urls.add(link)
                seen_titles.add(title)
                deck = entry.get("summary", "")
                deck = re.sub(r'<[^>]+>', '', deck).strip()[:1000]
                source_candidates[source].append({
                    "title": title,
                    "deck": deck,
                    "link": link,
                    "cat": feed_info["cat"],
                    "source": source,
                    "published_str": published_str,
                    "published_dt": dt,
                })
        except Exception as e:
            print(f"Error fetching {feed_info['url']}: {e}")

    new_items = []
    for source, candidates in source_candidates.items():
        count = 0
        for item in candidates:
            if count >= MAX_PER_SOURCE:
                break
            print(f"Processing [{source}]: {item['title'][:50]}...")
            cn_title, cn_deck, ai_cat = generate_cn_content(item['title'], item['deck'])
            if cn_title == "SKIP" or not cn_title:
                print(f"  Skipped.")
                continue
            dt = item["published_dt"]
            final_cat = ai_cat if ai_cat else item["cat"]
            new_items.append({
                "headline": item["title"],
                "deck": item["deck"],
                "cnTitle": cn_title,
                "cnDeck": cn_deck,
                "cat": final_cat,
                "source": source,
                "url": item["link"],
                "time": get_time_ago(dt),
                "published_iso": dt.isoformat() if dt else now.isoformat(),
                "is_new": True,
            })
            count += 1

    all_news = new_items + existing
    all_news.sort(key=lambda x: x.get("published_iso", ""), reverse=True)

    for i, item in enumerate(all_news):
        item["id"] = f"n{i+1}"
        item["lead"] = (i == 0)

    os.makedirs("data", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done: {len(all_news)} total ({len(new_items)} new + {len(existing)} retained)")


if __name__ == "__main__":
    fetch_news()
