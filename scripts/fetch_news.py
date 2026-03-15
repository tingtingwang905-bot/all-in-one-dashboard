import feedparser
import json
import os
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime

RSS_FEEDS = [
    {"url": "https://feeds.reuters.com/reuters/businessNews", "source": "Reuters", "cat": "economy"},
    {"url": "https://feeds.reuters.com/reuters/technologyNews", "source": "Reuters", "cat": "tech"},
    {"url": "http://feeds.bbci.co.uk/news/business/rss.xml", "source": "BBC", "cat": "economy"},
    {"url": "http://feeds.bbci.co.uk/news/technology/rss.xml", "source": "BBC", "cat": "tech"},
    {"url": "http://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC", "cat": "politics"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "source": "CNBC", "cat": "finance"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "source": "CNBC", "cat": "tech"},
]

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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

def generate_cn_summary(headline, deck, source):
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return ""
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
                    "content": f"用简洁中文（80字以内）概括以下新闻的核心内容，直接输出中文，不要任何前缀：\n标题：{headline}\n内容：{deck}"
                }]
            },
            timeout=15
        )
        data = response.json()
        print(f"API response: {str(data)[:200]}")
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenRouter API error: {e}")
        try:
            print(f"Response: {response.text[:200]}")
        except:
            pass
        return ""

def fetch_news():
    news = []
    seen = set()
    idx = 1

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:3]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)

                # 获取原文链接
                link = entry.get("link", "")
                if not link:
                    continue

                deck = entry.get("summary", "")
                # 清理 HTML 标签
                import re
                deck = re.sub(r'<[^>]+>', '', deck).strip()[:300]

                time_str = get_time_ago(entry.get("published", ""))

                # 生成中文摘要
                print(f"Generating CN summary for: {title[:50]}...")
                cn_summary = generate_cn_summary(title, deck, feed_info["source"])

                news.append({
                    "id": f"n{idx}",
                    "cat": feed_info["cat"],
                    "source": feed_info["source"],
                    "headline": title,
                    "deck": deck,
                    "cnSummary": cn_summary,
                    "time": time_str,
                    "url": link,
                    "lead": idx == 1
                })
                idx += 1
                if idx > 12:
                    break
        except Exception as e:
            print(f"Error fetching {feed_info['url']}: {e}")
        if idx > 12:
            break

    os.makedirs("data", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"Done: {len(news)} articles saved to data/news.json")

if __name__ == "__main__":
    fetch_news()
