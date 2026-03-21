import os
import json
import requests
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────
# 频道配置
# lang: "cn" = 中文频道, "en" = 英文频道
# ─────────────────────────────────────────
CHANNELS = [
    # ── 中文 ──
    {"name": "方方土",            "id": "UC-CckeotGQCZigg3nETreCQ", "lang": "cn"},
    {"name": "王志安",            "id": "UCBKDRq35-L8xev4O7ZqBeLg", "lang": "cn"},
    {"name": "马斯库",            "id": "UC3411UsjUC2t-Xfr1gwIhzg",  "lang": "cn"},
    {"name": "小Lin说",           "id": "UCilwQlk62k1z7aUEZPOB6yw",  "lang": "cn"},
    {"name": "小岛大浪吹",        "id": "UCYPT3wl0MgbOz63ho166KOw",  "lang": "cn"},
    {"name": "文昭谈古论今",      "id": "UCtAIPjABiQD3qjlEl1T5VpA",  "lang": "cn"},
    {"name": "柴静",              "id": "UCjuNibFJ21MiSNpu8LZyV4w",  "lang": "cn"},
    {"name": "自由亚洲电台",      "id": "UCnUYZLuoy1rq1aVMwx4aTzw",  "lang": "cn"},
    {"name": "美国之音中文",      "id": "UCt5zpwa264A0B-gaYtv1IpA",  "lang": "cn"},
    {"name": "马克时空",          "id": "UCejNr6vMTCstFMb-UisJRaw",  "lang": "cn"},
    # ── AI ──
    {"name": "Matt Wolfe",        "id": "UChpleBmo18P08aKCIgti38g",  "lang": "en"},
    {"name": "Tina Huang",        "id": "UC2UXDak6o7rBm23k3Vv5dww",  "lang": "en"},
    {"name": "Jeff Su",           "id": "UCwAnu01qlnVg1Ai2AbtTMaA",  "lang": "en"},
    {"name": "The AI Advantage",  "id": "UCHhYXsLBEVVnbvsq57n1MTQ",  "lang": "en"},
    {"name": "Linus Tech Tips",   "id": "UCXuqSBlHAE6Xw-yeJA0Tunw",  "lang": "en"},
    {"name": "跟李沐学AI",        "id": "UC8WCW6C3BWLKSZ5cMzD8Gyw",  "lang": "en"},
    {"name": "Andrej Karpathy",   "id": "UCXUPKJO5MZQN11PqgIvyuvQ",  "lang": "en"},
    {"name": "Hung-yi Lee",       "id": "UC2ggjtuuWvxrHHHiaDH1dlQ",  "lang": "en"},
    {"name": "Dwarkesh Patel",    "id": "UCXl4i9dYBrFOabk0xGmbkRA",  "lang": "en"},
    {"name": "The AI Daily Brief","id": "UCKelCK4ZaO6HeEI1KQjqzWA",  "lang": "en"},
]

KEEP_HOURS = 168         # 每次抓取过去7天的新视频（历史靠 merge 永久累积）
MAX_PER_CHANNEL = 20     # 每次每个频道最多抓取条数
MAX_TOTAL_PER_CHANNEL = 200  # 每个频道历史最多保留条数（防止文件无限增大）

API_KEY = os.environ.get("YOUTUBE_API_KEY")
BASE_URL = "https://www.googleapis.com/youtube/v3"


def get_channel_uploads_playlist(channel_id):
    url = f"{BASE_URL}/channels"
    params = {"part": "contentDetails,snippet", "id": channel_id, "key": API_KEY}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return None, None
    uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    thumbnail = items[0]["snippet"]["thumbnails"].get("default", {}).get("url", "")
    return uploads_id, thumbnail


def get_videos_within_window(playlist_id, cutoff):
    """从播放列表抓视频，只保留 cutoff 时间之后发布的"""
    url = f"{BASE_URL}/playlistItems"
    videos = []
    page_token = None

    while len(videos) < MAX_PER_CHANNEL:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 10,
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        for item in data.get("items", []):
            snippet = item["snippet"]
            published_str = snippet.get("publishedAt", "")
            if not published_str:
                continue
            try:
                published_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except Exception:
                continue

            # 超过时间窗口就停止（播放列表按时间倒序）
            if published_dt < cutoff:
                return videos

            vid_id = snippet.get("resourceId", {}).get("videoId", "")
            if not vid_id:
                continue

            thumbs = snippet.get("thumbnails", {})
            thumb = (
                thumbs.get("maxres", {}).get("url") or
                thumbs.get("high", {}).get("url") or
                thumbs.get("medium", {}).get("url") or
                thumbs.get("default", {}).get("url") or ""
            )

            videos.append({
                "id": vid_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:200],
                "thumbnail": thumb,
                "published_at": published_str,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "embed_url": f"https://www.youtube.com/embed/{vid_id}",
                "duration_seconds": None,
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return videos


def parse_duration(iso_duration):
    """解析 ISO 8601 时长，返回秒数。如 PT1H2M3S = 3723"""
    import re
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    m = re.match(pattern, iso_duration or '')
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def filter_long_videos(videos, api_key, min_seconds=300):
    """批量查询视频时长，过滤掉短于 min_seconds 的视频"""
    if not videos:
        return videos
    ids = [v["id"] for v in videos]
    durations = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i+50]
        try:
            r = requests.get(
                f"{BASE_URL}/videos",
                params={"part": "contentDetails", "id": ",".join(batch), "key": api_key},
                timeout=15
            )
            r.raise_for_status()
            for item in r.json().get("items", []):
                vid_id = item["id"]
                dur = item.get("contentDetails", {}).get("duration", "")
                durations[vid_id] = parse_duration(dur)
        except Exception as e:
            print(f"  ⚠️  Duration fetch error: {e}")

    filtered = []
    for v in videos:
        dur = durations.get(v["id"], 0)
        v["duration_seconds"] = dur
        if dur >= min_seconds:
            filtered.append(v)
        else:
            print(f"  ⏭️  Skipped short video ({dur}s): {v['title'][:40]}")
    print(f"  📹 {len(filtered)}/{len(videos)} videos ≥{min_seconds}s kept")
    return filtered


def fetch_all():
    if not API_KEY:
        raise ValueError("YOUTUBE_API_KEY environment variable not set")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=KEEP_HOURS)
    print(f"Fetching videos published after: {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    # ── 读取已有历史数据 ──
    existing_path = "data/videos.json"
    existing_channels = {}  # channel_id -> channel entry（含历史视频）

    if os.path.exists(existing_path):
        try:
            with open(existing_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            for ch in old_data.get("channels", []):
                existing_channels[ch["channel_id"]] = ch
            print(f"📂 Loaded existing data: {len(existing_channels)} channels, "
                  f"{sum(len(c['videos']) for c in existing_channels.values())} total videos")
        except Exception as e:
            print(f"⚠️  Could not load existing data (starting fresh): {e}")

    cn_channels = []
    en_channels = []

    for ch in CHANNELS:
        print(f"\nFetching: {ch['name']} ({ch['id']})")
        try:
            playlist_id, channel_thumb = get_channel_uploads_playlist(ch["id"])
            if not playlist_id:
                print(f"  ⚠️  Channel not found, skipping")
                continue

            # 抓取最新窗口内的视频
            new_videos = get_videos_within_window(playlist_id, cutoff)
            new_videos = filter_long_videos(new_videos, API_KEY, min_seconds=300)

            # ── Merge：新视频 + 历史视频去重合并 ──
            cid = ch["id"]
            old_videos = existing_channels.get(cid, {}).get("videos", [])
            old_ids = {v["id"] for v in old_videos}
            new_ids = {v["id"] for v in new_videos}

            # 新视频中不在历史里的才算新增
            added_count = len([v for v in new_videos if v["id"] not in old_ids])

            # 合并：新视频优先（覆盖同 id），旧视频补充
            merged_map = {v["id"]: v for v in old_videos}
            for v in new_videos:
                merged_map[v["id"]] = v  # 新数据覆盖旧数据（thumbnail 等可能更新）

            merged = list(merged_map.values())
            # 按发布时间倒序排列
            merged.sort(key=lambda v: v.get("published_at", ""), reverse=True)
            # 限制每频道最大保留条数，防止文件无限增大
            merged = merged[:MAX_TOTAL_PER_CHANNEL]

            print(f"  ➕ +{added_count} new  |  📚 {len(merged)} total stored")

            entry = {
                "channel_name": ch["name"],
                "channel_id": cid,
                "channel_thumb": channel_thumb,
                "lang": ch["lang"],
                "videos": merged,
            }

            if ch["lang"] == "cn":
                cn_channels.append(entry)
            else:
                en_channels.append(entry)

        except Exception as e:
            # 如果抓取失败，保留历史数据不丢失
            print(f"  ❌  Error: {e}")
            cid = ch["id"]
            if cid in existing_channels:
                old_entry = existing_channels[cid]
                print(f"  ♻️  Keeping existing {len(old_entry['videos'])} videos for {ch['name']}")
                if ch["lang"] == "cn":
                    cn_channels.append(old_entry)
                else:
                    en_channels.append(old_entry)

    # 合并，中文在前
    all_channels = cn_channels + en_channels
    total = sum(len(ch["videos"]) for ch in all_channels)

    output = {
        "updated_at": now.isoformat(),
        "keep_hours": KEEP_HOURS,
        "total_videos": total,
        "channels": all_channels,
    }

    os.makedirs("data", exist_ok=True)
    with open(existing_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done — {len(cn_channels)} CN + {len(en_channels)} EN channels, {total} videos total")


if __name__ == "__main__":
    fetch_all()
