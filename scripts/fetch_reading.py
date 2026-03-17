import feedparser
import json
import os
import requests
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ─────────────────────────────────────────
# 深度阅读来源配置
# ─────────────────────────────────────────
READING_FEEDS = [
    {
        "url": "https://www.economist.com/finance-and-economics/rss.xml",
        "pub": "The Economist", "pubKey": "economist", "pubColor": "#cc0000"
    },
    {
        "url": "https://www.economist.com/business/rss.xml",
        "pub": "The Economist", "pubKey": "economist", "pubColor": "#cc0000"
    },
    {
        "url": "https://www.economist.com/leaders/rss.xml",
        "pub": "The Economist", "pubKey": "economist", "pubColor": "#cc0000"
    },
    {
        "url": "https://www.technologyreview.com/feed/",
        "pub": "MIT Technology Review", "pubKey": "mit", "pubColor": "#750014"
    },
    {
        "url": "https://qz.com/feed/",
        "pub": "Quartz", "pubKey": "quartz", "pubColor": "#333333"
    },
]

MAX_PER_SOURCE = 4       # 每个来源最多保留几篇
KEEP_DAYS = 14           # 保留最近14天的文章


def parse_published(s):
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except:
        return None


def generate_reading_content(title, summary, url):
    """生成中文标题 + 1500字中英双语摘要"""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "", "", ""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-haiku-4-5",
                "max_tokens": 2500,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"以下是一篇深度文章，请完成三项任务：\n\n"
                        f"任务一：给出15字以内的中文标题\n\n"
                        f"任务二：用英文写3个完整自然段的摘要，每段至少150字，共500字以上。要求：\n"
                        f"- 第一段：文章核心论点和背景\n"
                        f"- 第二段：关键数据、案例、引语\n"
                        f"- 第三段：结论与影响\n"
                        f"- 紧贴原文，保留数字、人名、直接引语，读起来像原文精简版\n"
                        f"- 段落之间用空行分隔\n\n"
                        f"任务三：用中文写对应的3段摘要，与英文版结构一致，每段至少150字，共500字以上\n"
                        f"- 段落之间用空行分隔\n\n"
                        f"严格按以下格式输出，不要加任何额外标签：\n"
                        f"[中文标题]\n"
                        f"---EN---\n"
                        f"[英文摘要]\n"
                        f"---CN---\n"
                        f"[中文摘要]\n\n"
                        f"文章标题：{title}\n"
                        f"文章内容：{summary[:1000]}"
                    )
                }]
            },
            timeout=30
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # 解析格式
        parts = content.split("---EN---")
        if len(parts) < 2:
            return "", "", ""

        cn_title = parts[0].strip()
        rest = parts[1].split("---CN---")
        en_summary = rest[0].strip() if len(rest) > 0 else ""
        cn_summary = rest[1].strip() if len(rest) > 1 else ""

        # 清理标题
        for prefix in ['标题：', '标题:', '中文标题：', '[', ']']:
            cn_title = cn_title.replace(prefix, '').strip()

        if len(cn_title) < 3 or len(en_summary) < 100:
            return "", "", ""

        print(f"  ✅ '{cn_title[:25]}' | EN:{len(en_summary)}chars CN:{len(cn_summary)}chars")
        return cn_title, en_summary, cn_summary

    except Exception as e:
        print(f"  API error: {e}")
        return "", "", ""


def estimate_read_time(text):
    words = len(text.split())
    minutes = max(1, round(words / 200))
    return f"{minutes} min"


def fetch_reading():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=KEEP_DAYS)

    # ── 加载历史数据 ──
    existing = []
    existing_urls = set()
    try:
        with open("data/reading.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing = [
            item for item in existing
            if item.get("published_iso") and
               datetime.fromisoformat(item["published_iso"]) >= cutoff
        ]
        existing_urls = {item["url"] for item in existing}
        print(f"Loaded {len(existing)} existing articles within {KEEP_DAYS} days")
    except Exception as e:
        print(f"No existing reading.json or parse error: {e}")

    # ── 抓取新文章 ──
    source_candidates = {}

    for feed_info in READING_FEEDS:
        key = feed_info["pubKey"]
        if key not in source_candidates:
            source_candidates[key] = {
                "pub": feed_info["pub"],
                "pubKey": feed_info["pubKey"],
                "pubColor": feed_info["pubColor"],
                "items": []
            }
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:10]:
                url = entry.get("link", "")
                if not url or url in existing_urls:
                    continue
                title = entry.get("title", "").strip()
                if not title:
                    continue
                published_str = entry.get("published", "")
                dt = parse_published(published_str)
                if dt and dt < cutoff:
                    continue
                summary = entry.get("summary", "") or entry.get("description", "")
                summary = re.sub(r'<[^>]+>', '', summary).strip()
                source_candidates[key]["items"].append({
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "published_dt": dt,
                    "published_str": published_str,
                })
        except Exception as e:
            print(f"Error fetching {feed_info['url']}: {e}")

    # ── AI 处理 ──
    new_articles = []
    for key, src in source_candidates.items():
        count = 0
        for item in src["items"]:
            if count >= MAX_PER_SOURCE:
                break
            print(f"Processing [{src['pub']}]: {item['title'][:50]}...")
            cn_title, en_summary, cn_summary = generate_reading_content(
                item["title"], item["summary"], item["url"]
            )
            if not cn_title:
                print(f"  Skipped (no valid output)")
                continue

            dt = item["published_dt"]
            new_articles.append({
                "pub": src["pub"],
                "pubKey": src["pubKey"],
                "pubColor": src["pubColor"],
                "headline": item["title"],       # 英文原标题
                "cnTitle": cn_title,              # 中文标题
                "lede": item["summary"][:200],    # 原文导言
                "enSummary": en_summary,          # 英文摘要
                "cnSummary": cn_summary,          # 中文摘要
                "readtime": estimate_read_time(en_summary),
                "url": item["url"],
                "published_iso": dt.isoformat() if dt else now.isoformat(),
            })
            count += 1
            existing_urls.add(item["url"])

    # ── 合并排序 ──
    all_articles = new_articles + existing
    all_articles.sort(key=lambda x: x.get("published_iso", ""), reverse=True)

    os.makedirs("data", exist_ok=True)
    with open("data/reading.json", "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done: {len(all_articles)} articles ({len(new_articles)} new + {len(existing)} retained)")


if __name__ == "__main__":
    fetch_reading()
