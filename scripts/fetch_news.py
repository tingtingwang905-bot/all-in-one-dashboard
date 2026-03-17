import feedparser
import json
import os
import requests
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

RSS_FEEDS = [
    {"url": "http://feeds.bbci.co.uk/news/business/rss.xml", "source": "BBC", "cat": "economy"},
    {"url": "http://feeds.bbci.co.uk/news/technology/rss.xml", "source": "BBC", "cat": "tech"},
    {"url": "http://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC", "cat": "politics"},
    {"url": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "source": "BBC", "cat": "tech"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "source": "CNBC", "cat": "finance"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "source": "CNBC", "cat": "tech"},
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135", "source": "CNBC", "cat": "finance"},
    {"url": "https://news.google.com/rss/search?q=when:48h+allinurl:bloomberg.com&ceid=US:en&hl=en-US&gl=US", "source": "Bloomberg", "cat": "finance"},
    {"url": "https://news.google.com/rss/search?q=when:48h+allinurl:bloomberg.com+technology&ceid=US:en&hl=en-US&gl=US", "source": "Bloomberg", "cat": "tech"},
]

MAX_PER_SOURCE = 10   # 每个媒体最多10条
KEEP_HOURS = 48       # 保留过去48小时

def parse_published(published_str):
    """解析发布时间，返回 UTC datetime，失败返回 None"""
    try:
        return parsedate_to_datetime(published_str).astimezone(timezone.utc)
    except:
        return None

def get_time_ago(dt):
    """dt 是 UTC datetime，返回中文时间描述"""
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

def generate_cn_content(headline, deck):
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "SKIP", ""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-haiku-4-5",
                "max_tokens": 300,
                "messages": [{
                    "role": "user",
                   "content": f"判断以下新闻是否值得关注。\n只保留：重大地缘政治事件、全球金融市场动态、科技巨头重要动态、央行货币政策、重大经济数据、战争冲突、重要人物言论。\n不要：本地小事、娱乐体育、消费提示、交通延误、地方政策、动物故事、软性生活内容。\n如果值得关注，输出三行：\n第一行：15字以内的中文标题，不含任何前缀\n第二行：200字以内的中文摘要，不含任何前缀\n第三行：分类，只能从以下四个选一个：economy / tech / finance / politics\n分类说明：economy=宏观经济/央行/贸易，tech=科技/AI/芯片/互联网公司，finance=金融市场/股票/外汇/加密货币，politics=地缘政治/战争/选举\n如果不值得关注，只回复：SKIP\n直接输出，不要任何前缀标签：\n标题：{headline}\n内容：{deck}"
                }]
            },
            timeout=15
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        if "SKIP" in content.upper() or "不值得" in content or "无需关注" in content or len(content) < 5:
            return "SKIP", ""
      lines = [l.strip() for l in content.split('\n') if l.strip()]
cn_title = lines[0] if len(lines) > 0 else ""
cn_deck  = lines[1] if len(lines) > 1 else ""
ai_cat   = lines[2].lower() if len(lines) > 2 else ""
# 验证分类合法
if ai_cat not in ('economy', 'tech', 'finance', 'politics'):
    ai_cat = ""
        for prefix in ['摘要：', '第二行：', '中文摘要']:
            cn_deck = cn_deck.replace(prefix, '').strip()
        print(f"cnTitle: {cn_title[:30]}")
        return cn_title, cn_deck
    except Exception as e:
        print(f"API error: {e}")
        return "", ""

def fetch_news():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=KEEP_HOURS)

    # ── 加载现有历史数据 ──────────────────────────────
    existing = []
    existing_headlines = set()
    try:
        with open("data/news.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
        # 过滤掉超过48小时的旧数据
        existing = [
            item for item in existing
            if item.get("published_iso") and
               datetime.fromisoformat(item["published_iso"]) >= cutoff
        ]
        existing_headlines = {item["headline"] for item in existing}
        print(f"Loaded {len(existing)} items from existing news.json (within 48h)")
    except Exception as e:
        print(f"No existing news.json or parse error: {e}")

    # ── 抓取新内容 ────────────────────────────────────
    source_candidates = {}
    seen_titles = set(existing_headlines)

    for feed_info in RSS_FEEDS:
        source = feed_info["source"]
        if source not in source_candidates:
            source_candidates[source] = []
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:20]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                published_str = entry.get("published", "")
                dt = parse_published(published_str)
                # 只取48小时内的新闻
                if dt and dt < cutoff:
                    continue
                seen_titles.add(title)
                link = entry.get("link", "")
                if not link:
                    continue
                deck = entry.get("summary", "")
                deck = re.sub(r'<[^>]+>', '', deck).strip()[:300]
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

    # ── AI 筛选新条目 ─────────────────────────────────
    new_items = []
    for source, candidates in source_candidates.items():
        count = 0
        for item in candidates:
            if count >= MAX_PER_SOURCE:
                break
            print(f"Processing [{source}]: {item['title'][:50]}...")
            cn_title, cn_deck = generate_cn_content(item['title'], item['deck'])
            if cn_title == "SKIP":
                print(f"  Skipped.")
                continue
            dt = item["published_dt"]
            new_items.append({
                "headline": item["title"],
                "deck": item["deck"],
                "cnTitle": cn_title,
                "cnDeck": cn_deck,
                "cat": ai_cat if ai_cat else item["cat"],
                "source": source,
                "url": item["link"],
                "time": get_time_ago(dt),
                "published_iso": dt.isoformat() if dt else now.isoformat(),
            })
            count += 1

    # ── 合并：新内容 + 历史48小时内容，按时间排序 ────
    all_news = new_items + existing
    all_news.sort(
        key=lambda x: x.get("published_iso", ""),
        reverse=True  # 最新在前
    )

    # 重新分配 id，确保 lead 是第一条
    for i, item in enumerate(all_news):
        item["id"] = f"n{i+1}"
        item["lead"] = (i == 0)

    os.makedirs("data", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done: {len(all_news)} total articles ({len(new_items)} new + {len(existing)} retained from past 48h)")

if __name__ == "__main__":
    fetch_news()
