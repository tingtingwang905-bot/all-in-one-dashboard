import feedparser
import json
import os
import requests
from datetime import datetime

# RSS 源
RSS_FEEDS = [
    {"url": "https://feeds.reuters.com/reuters/businessNews", "source": "Reuters", "cat": "economy"},
    {"url": "https://feeds.reuters.com/reuters/technologyNews", "source": "Reuters", "cat": "tech"},
    {"url": "https://feeds.bloomberg.com/markets/news.rss", "source": "Bloomberg", "cat": "finance"},
    {"url": "http://feeds.bbci.co.uk/news/business/rss.xml", "source": "BBC", "cat": "economy"},
    {"url": "http://feeds.bbci.co.uk/news/technology/rss.xml", "source": "BBC", "cat": "tech"},
    {"url": "http://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC", "cat": "politics"},
]

def fetch_news():
    news = []
    seen = set()
    idx = 1

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:3]:  # 每个源取3条
                title = entry.get("title", "").strip()
                if title in seen:
                    continue
                seen.add(title)

                # 时间处理
                published = entry.get("published", "")
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(published)
                    now = datetime.utcnow().replace(tzinfo=dt.tzinfo)
                    diff = now - dt
                    hours = int(diff.total_seconds() / 3600)
                    time_str = f"{hours}h ago" if hours > 0 else "Just now"
                except:
                    time_str = "Today"

                news.append({
                    "id": f"n{idx}",
                    "cat": feed_info["cat"],
                    "source": feed_info["source"],
                    "headline": title,
                    "deck": entry.get("summary", "")[:200],
                    "time": time_str,
                    "url": entry.get("link", "#"),
                    "lead": idx == 1
                })
                idx += 1

        except Exception as e:
            print(f"Error fetching {feed_info['url']}: {e}")

    # 用 Claude API 生成中文摘要（可选）
    # 保存 JSON
    os.makedirs("data", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news[:10], f, ensure_ascii=False, indent=2)

    print(f"Updated news.json with {len(news[:10])} articles")

if __name__ == "__main__":
    fetch_news()
