import feedparser
import json
import os
import requests
import re
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

# 无效标题集合
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
    """清理标题，去除所有可能的前缀和括号"""
    t = raw.strip()
    # 去除方括号
    t = t.strip('[]【】')
    # 去除各种前缀
    for prefix in ['标题：', '标题:', '第一行：', '第一行:', '中文标题：',
                   '中文标题:', '一、', '1. ', '1、', 'Title:', 'title:']:
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    # 如果还有冒号且总长度很短，取冒号后面部分
    if '：' in t and len(t) < 20:
        t = t.split('：', 1)[-1].strip()
    # 如果太长（超过30字）说明是摘要内容混进来了，直接丢弃
    if len(t) > 30:
        return ""
    # 验证是否有效
    if t.lower() in INVALID_TITLES or len(t) < 3:
        return ""
    return t


def generate_cn_content(headline, deck):
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "SKIP", "", ""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-haiku-4-5",
                "max_tokens": 600,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"判断以下新闻是否值得关注。\n"
                        f"只保留：重大地缘政治事件、全球金融市场动态、科技巨头重要动态、央行货币政策、重大经济数据、战争冲突、重要人物言论。\n"
                        f"不要：本地小事、娱乐体育、消费提示、交通延误、地方政策、动物故事、软性生活内容。\n"
                        f"严格按以下格式输出，共三行，每行之间用换行分隔，不加任何前缀标签：\n"
                        f"[中文标题，15字以内]\n"
                        f"[原文直译，保留数字/人名/机构名/引语，300字以内，不要总结归纳]\n"
                        f"[分类：economy 或 tech 或 finance 或 politics 其中一个]\n"
                        f"分类说明：economy=宏观经济/央行/贸易/通胀，tech=科技/AI/芯片/互联网，"
                        f"finance=金融市场/股票/外汇/加密/银行，politics=地缘政治/战争/选举/外交\n"
                        f"如果不值得关注，只回复：SKIP\n\n"
                        f"新闻标题：{headline}\n"
                        f"新闻内容：{deck}"
                    )
                }]
            },
            timeout=15
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        if "SKIP" in content.upper() or "不值得" in content or "无需关注" in content or len(content) < 5:
            return "SKIP", "", ""

        # 解析三行
        lines = [l.strip() for l in content.split('\n') if l.strip()]

        if len(lines) < 1:
            return "SKIP", "", ""

        # 清理并验证标题
        cn_title = clean_title(lines[0])
        if not cn_title:
            print(f"  Invalid title after cleaning: '{lines[0]}', skipping")
            return "SKIP", "", ""

        cn_deck = lines[1] if len(lines) > 1 else ""
        ai_cat  = lines[2].lower() if len(lines) > 2 else ""

        # 清理摘要前缀
        for prefix in ['摘要：', '摘要:', '第二行：', '中文摘要：', '翻译：', '内容：']:
            cn_deck = cn_deck.replace(prefix, '').strip()

        # 清理分类前缀并验证
        for prefix in ['分类：', '分类:', '第三行：', 'category:', 'Category:']:
            ai_cat = ai_cat.replace(prefix, '').strip()
        if ai_cat not in ('economy', 'tech', 'finance', 'politics'):
            ai_cat = ""

        print(f"  ✅ '{cn_title[:25]}' | cat={ai_cat}")
        return cn_title, cn_deck, ai_cat

    except Exception as e:
        print(f"  API error: {e}")
        return "", "", ""


def fetch_news():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=KEEP_HOURS)

    # ── 加载历史数据，保留48小时内的 ──
    existing = []
    existing_headlines = set()
    try:
        with open("data/news.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing = [
            item for item in existing
            if item.get("published_iso") and
               datetime.fromisoformat(item["published_iso"]) >= cutoff
        ]
        existing_headlines = {item["headline"] for item in existing}
        print(f"Loaded {len(existing)} existing items within 48h")
    except Exception as e:
        print(f"No existing news.json or parse error: {e}")

    # ── 抓取新内容 ──
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

    # ── AI 筛选 + 分类 ──
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
            })
            count += 1

    # ── 合并新旧，按时间排序 ──
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
