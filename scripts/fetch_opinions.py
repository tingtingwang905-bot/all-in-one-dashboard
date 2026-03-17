import json
import os
import requests
import re
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────
# 人物配置
# ─────────────────────────────────────────
PEOPLE = [
    # 商界
    {"id": "elon_musk",      "name": "Elon Musk",         "nameZh": "马斯克",       "role": "Tesla / SpaceX / xAI CEO", "cat": "biz",     "color": "#1a1a1a",
     "search": "Elon Musk said statement interview 2026"},
    {"id": "jensen_huang",   "name": "Jensen Huang",      "nameZh": "黄仁勋",       "role": "NVIDIA CEO",               "cat": "biz",     "color": "#76b900",
     "search": "Jensen Huang NVIDIA said statement 2026"},
    {"id": "satya_nadella",  "name": "Satya Nadella",     "nameZh": "萨提亚·纳德拉","role": "Microsoft CEO",            "cat": "biz",     "color": "#0078d4",
     "search": "Satya Nadella Microsoft said statement 2026"},
    {"id": "sam_altman",     "name": "Sam Altman",        "nameZh": "萨姆·奥特曼",  "role": "OpenAI CEO",               "cat": "biz",     "color": "#10a37f",
     "search": "Sam Altman OpenAI said statement interview 2026"},
    {"id": "jamie_dimon",    "name": "Jamie Dimon",       "nameZh": "杰米·戴蒙",    "role": "JPMorgan Chase CEO",       "cat": "biz",     "color": "#003087",
     "search": "Jamie Dimon JPMorgan said statement 2026"},
    {"id": "dario_amodei",   "name": "Dario Amodei",      "nameZh": "达里奥·阿莫迪","role": "Anthropic CEO",            "cat": "biz",     "color": "#c41230",
     "search": "Dario Amodei Anthropic said statement interview 2026"},
    # 投资界
    {"id": "warren_buffett", "name": "Warren Buffett",    "nameZh": "沃伦·巴菲特",  "role": "Berkshire Hathaway Chairman","cat": "invest", "color": "#b5872a",
     "search": "Warren Buffett said statement letter interview 2026"},
    {"id": "schwarzman",     "name": "Stephen Schwarzman","nameZh": "苏世民",        "role": "Blackstone Chairman & CEO","cat": "invest",  "color": "#1a3a5c",
     "search": "Stephen Schwarzman Blackstone said statement 2026"},
    {"id": "cathie_wood",    "name": "Cathie Wood",       "nameZh": "凯茜·伍德",    "role": "ARK Invest CEO",           "cat": "invest",  "color": "#6a0dad",
     "search": "Cathie Wood ARK said statement interview 2026"},
    {"id": "larry_fink",     "name": "Larry Fink",        "nameZh": "拉里·芬克",    "role": "BlackRock CEO",            "cat": "invest",  "color": "#2c2c2c",
     "search": "Larry Fink BlackRock said statement letter 2026"},
    {"id": "duan_yongping",  "name": "Duan Yongping",     "nameZh": "段永平",        "role": "Investor / OPPO & BBK Founder","cat": "invest","color": "#e07b00",
     "search": "段永平 观点 投资 2026"},
    # 科学界
    {"id": "fei_fei_li",     "name": "Fei-Fei Li",        "nameZh": "李飞飞",        "role": "Stanford HAI Co-Director", "cat": "science", "color": "#8b1a1a",
     "search": "Fei-Fei Li Stanford AI said statement 2026"},
    {"id": "hinton",         "name": "Geoffrey Hinton",   "nameZh": "杰弗里·辛顿",  "role": "Nobel Laureate / AI Pioneer","cat": "science","color": "#1a4a1a",
     "search": "Geoffrey Hinton AI said statement interview 2026"},
]

KEEP_MONTHS = 6    # 保留最近6个月的观点
SEARCH_DAYS = 30   # 每次搜索最近30天的新观点


def search_person_quotes(person):
    """用 Google News RSS 搜索人物最新言论"""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return []

    query = person["search"].replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={query}&ceid=US:en&hl=en-US&gl=US&num=5"

    try:
        import feedparser
        feed = feedparser.parse(url)
        articles = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=SEARCH_DAYS)

        for entry in feed.entries[:8]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "") or ""
            summary = re.sub(r'<[^>]+>', '', summary).strip()
            link = entry.get("link", "")
            published_str = entry.get("published", "")

            # 解析时间
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(published_str).astimezone(timezone.utc)
                if dt < cutoff:
                    continue
            except:
                dt = datetime.now(timezone.utc)

            articles.append({
                "title": title,
                "summary": summary,
                "url": link,
                "dt": dt,
            })
        return articles
    except Exception as e:
        print(f"  Search error: {e}")
        return []


def extract_quote(person, articles):
    """让 AI 从搜索结果中提取最有价值的观点，中英双语"""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key or not articles:
        return None

    articles_text = "\n\n".join([
        f"标题: {a['title']}\n内容: {a['summary'][:300]}\n来源: {a['url']}"
        for a in articles[:5]
    ])

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-haiku-4-5",
                "max_tokens": 800,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"以下是关于 {person['name']}（{person['nameZh']}，{person['role']}）最近的新闻报道。\n"
                        f"请从中提取最具价值的一段核心观点或言论。\n\n"
                        f"要求：\n"
                        f"1. 找出他/她最近表达的最重要观点（可以是直接引语或意思概括）\n"
                        f"2. 必须是真实可查的内容，不要编造\n"
                        f"3. 如果没有找到有价值的观点，回复：SKIP\n\n"
                        f"如果找到，严格按以下格式输出：\n"
                        f"[英文原文观点，150字以内，尽量用直接引语]\n"
                        f"---CN---\n"
                        f"[中文翻译，150字以内，保留直接引语风格]\n"
                        f"---SOURCE---\n"
                        f"[来源名称，如 Bloomberg Interview / X (Twitter) / Annual Letter 等]\n\n"
                        f"新闻内容：\n{articles_text}"
                    )
                }]
            },
            timeout=20
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        if "SKIP" in content.upper() or len(content) < 20:
            return None

        # 解析格式
        parts = content.split("---CN---")
        if len(parts) < 2:
            return None

        en_quote = parts[0].strip().strip("[]")
        rest = parts[1].split("---SOURCE---")
        cn_quote = rest[0].strip().strip("[]")
        source = rest[1].strip().strip("[]") if len(rest) > 1 else "Media Report"

        if len(en_quote) < 20 or len(cn_quote) < 10:
            return None

        # 找最新文章的 URL
        best_url = articles[0]["url"] if articles else ""
        best_dt = articles[0]["dt"] if articles else datetime.now(timezone.utc)

        print(f"  ✅ Found quote: '{en_quote[:50]}...'")
        return {
            "enQuote": en_quote,
            "cnQuote": cn_quote,
            "source": source,
            "url": best_url,
            "date": best_dt.strftime("%b %d, %Y"),
            "published_iso": best_dt.isoformat(),
        }

    except Exception as e:
        print(f"  AI error: {e}")
        return None


def fetch_opinions():
    now = datetime.now(timezone.utc)
    cutoff_6m = now - timedelta(days=180)   # 6个月保留线
    cutoff_search = now - timedelta(days=30) # 搜索最近1个月

    # ── 加载历史数据，保留6个月内的 ──
    existing_by_person = {}
    try:
        with open("data/opinions.json", "r", encoding="utf-8") as f:
            existing_raw = json.load(f)
        for item in existing_raw:
            pid = item.get("id", "")
            if not pid:
                continue
            iso = item.get("published_iso", "")
            if iso:
                try:
                    dt = datetime.fromisoformat(iso)
                    if dt < cutoff_6m:
                        continue   # 超过6个月，丢弃
                except:
                    pass
            if pid not in existing_by_person:
                existing_by_person[pid] = []
            existing_by_person[pid].append(item)
        total_existing = sum(len(v) for v in existing_by_person.values())
        print(f"Loaded {total_existing} existing opinions within 6 months")
    except Exception as e:
        print(f"No existing opinions.json or parse error: {e}")

    # ── 为每个人搜索最新观点 ──
    all_opinions = []

    for person in PEOPLE:
        print(f"\nProcessing: {person['name']} ({person['nameZh']})")

        # 已有的历史观点
        history = existing_by_person.get(person["id"], [])

        # 搜索最新1个月的观点
        articles = search_person_quotes(person)
        print(f"  Found {len(articles)} recent articles")

        new_quote = None
        if articles:
            new_quote = extract_quote(person, articles)

        # 合并：新观点 + 历史观点（去重）
        person_opinions = []

        if new_quote:
            person_opinions.append({
                "id": person["id"],
                "cat": person["cat"],
                "name": person["name"],
                "nameZh": person["nameZh"],
                "role": person["role"],
                "color": person["color"],
                # 双语观点
                "quote": new_quote["enQuote"],       # 英文（前端显示）
                "quoteZh": new_quote["cnQuote"],     # 中文
                "source": new_quote["source"],
                "url": new_quote["url"],
                "date": new_quote["date"],
                "published_iso": new_quote["published_iso"],
                "is_new": True,
            })

        # 加入历史（最多保留每人6条历史观点）
        for h in history[:6]:
            # 避免重复（同一来源同一时期）
            if new_quote and h.get("date") == (new_quote["date"] if new_quote else ""):
                continue
            person_opinions.append(h)

        # 如果完全没有数据，用代码里的静态数据兜底
        if not person_opinions:
            print(f"  ⚠️  No data found, using fallback")
            person_opinions.append(get_fallback(person))

        all_opinions.extend(person_opinions)

    # 按时间排序（最新在前）
    all_opinions.sort(key=lambda x: x.get("published_iso", ""), reverse=True)

    os.makedirs("data", exist_ok=True)
    with open("data/opinions.json", "w", encoding="utf-8") as f:
        json.dump(all_opinions, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done: {len(all_opinions)} total opinion entries")


def get_fallback(person):
    """兜底静态数据，确保每人至少有一条"""
    FALLBACKS = {
        "elon_musk":     {"en": "Whoever controls the most compute controls the future of intelligence.", "cn": "谁掌握最多算力，谁就掌控智能的未来。", "src": "X (Twitter)"},
        "jensen_huang":  {"en": "Every company is now an AI company. Physical AI is the next wave.", "cn": "每家公司现在都是AI公司。实体AI是下一波浪潮。", "src": "GTC Keynote"},
        "satya_nadella": {"en": "We are moving from AI as a tool to AI as an agent.", "cn": "我们正在从AI作为工具转向AI作为代理。", "src": "Microsoft Build"},
        "sam_altman":    {"en": "I believe we will achieve AGI within the next few years.", "cn": "我相信我们将在未来几年内实现AGI。", "src": "Bloomberg Interview"},
        "jamie_dimon":   {"en": "Geopolitical risk is at a level I haven't seen in my career.", "cn": "地缘政治风险处于我职业生涯中从未见过的水平。", "src": "JPMorgan Annual Letter"},
        "dario_amodei":  {"en": "We genuinely believe we might be building one of the most dangerous technologies ever.", "cn": "我们真心认为自己可能正在构建有史以来最危险的技术之一。", "src": "Lex Fridman Podcast"},
        "warren_buffett":{"en": "America's best days are still ahead. Don't bet against America.", "cn": "美国最好的日子还在前头。不要押注美国会失败。", "src": "Berkshire Annual Letter"},
        "schwarzman":    {"en": "We are entering a golden age for private credit and infrastructure.", "cn": "我们正在进入私人信贷和基础设施的黄金时代。", "src": "Davos"},
        "cathie_wood":   {"en": "The convergence of AI, robotics and genomics is creating a $200 trillion opportunity.", "cn": "AI、机器人和基因组学的融合正在创造200万亿美元的机会。", "src": "ARK Big Ideas"},
        "larry_fink":    {"en": "Infrastructure investment is the single most important asset class for the next 20 years.", "cn": "基础设施投资是未来20年最重要的资产类别。", "src": "BlackRock Annual Letter"},
        "duan_yongping": {"en": "投资的本质是买未来现金流，其他都是噪音。", "cn": "投资的本质是买未来现金流，其他都是噪音。", "src": "雪球访谈"},
        "fei_fei_li":    {"en": "The next frontier is machines that can perceive, reason, and act in 3D space.", "cn": "下一个前沿是能够在三维空间中感知、推理和行动的机器。", "src": "TED 2025"},
        "hinton":        {"en": "I am genuinely frightened. These systems are learning to manipulate people.", "cn": "我真的感到恐惧。这些系统正在学会操控人类。", "src": "60 Minutes Interview"},
    }
    fb = FALLBACKS.get(person["id"], {"en": "No recent quote available.", "cn": "暂无最新观点。", "src": "N/A"})
    return {
        "id": person["id"],
        "cat": person["cat"],
        "name": person["name"],
        "nameZh": person["nameZh"],
        "role": person["role"],
        "color": person["color"],
        "quote": fb["en"],
        "quoteZh": fb["cn"],
        "source": fb["src"],
        "url": "",
        "date": "2025",
        "published_iso": "2025-01-01T00:00:00+00:00",
        "is_new": False,
    }


if __name__ == "__main__":
    fetch_opinions()
