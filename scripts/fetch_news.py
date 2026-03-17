import feedparser
import json
import os
import requests
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

RSS_FEEDS = [
    {"url": "https://feeds.reuters.com/reuters/businessNews", "source": "Reuters", "cat": "economy"},
    {"url": "https://feeds.reuters.com/reuters/technologyNews", "source": "Reuters", "cat": "tech"},
    {"url": "https://feeds.reuters.com/reuters/worldNews", "source": "Reuters", "cat": "politics"},
    {"url": "http://feeds.bbci.co.uk/news/business/rss.xml", "source": "BBC", "cat": "economy"},
    {"url": "http://feeds.bbci.co.uk/news/technology/rss.xml", "source": "BBC", "cat": "tech"},
    {"url": "http://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC", "cat": "politics"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "source": "CNBC", "cat": "finance"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "source": "CNBC", "cat": "tech"},
    {"url": "https://feeds.ft.com/rss/home/uk", "source": "FT", "cat": "finance"},
    {"url": "https://www.wsj.com/xml/rss/3_7085.xml", "source": "WSJ", "cat": "finance"},
    {"url": "https://feeds.bloomberg.com/markets/news.rss", "source": "Bloomberg", "cat": "finance"},
]

def get_time_ago(published):
    try:
        dt = parsedate_to_datetime(published)
        now = datetime.utcnow().replace(tzinfo=dt.tzinfo)
        diff = now - dt
        hours = int(diff.total_seconds() / 3600)
        if hours < 1:
            return "刚刚"
        elif hours < 24:
            return f"{hours}小时前"
        else:
            days = hours // 24
            return f"{days}天前"
    except:
        return "今天"

def generate_cn_content(headline, deck):
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "", ""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-haiku-4-5",
                "max_tokens": 200,
                "messages": [{
                    "role": "user",
                    "content": f"针对以下新闻，请输出两行：\n第一行：15字以内的中文标题\n第二行：200字以内的中文摘要\n不要任何前缀和标签，直接输出两行：\n标题：{headline}\n内容：{deck}"
                }]
            },
            timeout=15
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        lines = content.split('\n', 1)
        cn_title = lines[0].strip()
        cn_deck = lines[1].strip() if len(lines) > 1 else ""
        print(f"cnTitle: {cn_title[:30]}")
        return cn_title, cn_deck
    except Exception as e:
        print(f"API error: {e}")
        return "", ""

def fetch_news():
    news = []
    seen = set()
    idx = 1

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:4]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)

                link = entry.get("link", "")
                if not link:
                    continue

                deck = entry.get("summary", "")
                deck = re.sub(r'<[^>]+>', '', deck).strip()[:300]
                time_str = get_time_ago(entry.get("published", ""))

                print(f"Processing: {title[:50]}...")
                cn_title, cn_deck = generate_cn_content(title, deck)

                news.append({
                    "id": f"n{idx}",
                    "cat": feed_info["cat"],
                    "source": feed_info["source"],
                    "headline": title,
                    "deck": deck,
                    "cnTitle": cn_title,
                    "cnDeck": cn_deck,
                    "time": time_str,
                    "url": link,
                    "lead": idx == 1
                })
                idx += 1
                if idx > 40:
                    break
        except Exception as e:
            print(f"Error: {e}")
        if idx > 40:
            break

    os.makedirs("data", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"Done: {len(news)} articles")

if __name__ == "__main__":
    fetch_news()
