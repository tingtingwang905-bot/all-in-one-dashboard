import os
import json
import requests
from datetime import datetime, timezone

# ─────────────────────────────────────────
# 频道配置
# lang: "cn" = 中文频道, "en" = 英文频道
# ─────────────────────────────────────────
CHANNELS = [
    # ── 中文 ──

    {"name": "王志安",            "id": "UCBKDRq35-L8xev4O7ZqBeLg", "lang": "cn"},
    {"name": "柴静",              "id": "UCjuNibFJ21MiSNpu8LZyV4w",  "lang": "cn"},
    {"name": "马斯库",            "id": "UC3411UsjUC2t-Xfr1gwIhzg",  "lang": "cn"},
    {"name": "马克时空",          "id": "UCejNr6vMTCstFMb-UisJRaw",  "lang": "cn"},
    {"name": "小Lin说",           "id": "UCilwQlk62k1z7aUEZPOB6yw",  "lang": "cn"},
    {"name": "小岛大浪吹",        "id": "UCYPT3wl0MgbOz63ho166KOw",  "lang": "cn"},
    {"name": "文昭谈古论今",      "id": "UCtAIPjABiQD3qjlEl1T5VpA",  "lang": "cn"},
    {"name": "自由亚洲电台",      "id": "UCnUYZLuoy1rq1aVMwx4aTzw",  "lang": "cn"},
    {"name": "美国之音中文",      "id": "UCt5zpwa264A0B-gaYtv1IpA",  "lang": "cn"},
    {"name": "方方土",            "id": "UC-CckeotGQCZigg3nETreCQ", "lang": "cn"},
    # ── AI ──
    {"name": "Matt Wolfe",        "id": "UChpleBmo18P08aKCIgti38g",  "lang": "en"},
    {"name": "Tina Huang",        "id": "UC2UXDak6o7rBm23k3Vv5dww",  "lang": "en"},
    {"name": "The AI Advantage",  "id": "UCHhYXsLBEVVnbvsq57n1MTQ",  "lang": "en"},
    {"name": "Andrej Karpathy",   "id": "UCXUPKJO5MZQN11PqgIvyuvQ",  "lang": "en"},
    {"name": "Jeff Su",           "id": "UCwAnu01qlnVg1Ai2AbtTMaA",  "lang": "en"},
    {"name": "Linus Tech Tips",   "id": "UCXuqSBlHAE6Xw-yeJA0Tunw",  "lang": "en"},
    {"name": "跟李沐学AI",        "id": "UC8WCW6C3BWLKSZ5cMzD8Gyw",  "lang": "en"},
    {"name": "Hung-yi Lee",       "id": "UC2ggjtuuWvxrHHHiaDH1dlQ",  "lang": "en"},
    {"name": "Dwarkesh Patel",    "id": "UCXl4i9dYBrFOabk0xGmbkRA",  "lang": "en"},
    {"name": "The AI Daily Brief","id": "UCKelCK4ZaO6HeEI1KQjqzWA",  "lang": "en"},
]

MAX_PER_CHANNEL = 50

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


def get_all_videos(playlist_id):
    url = f"{BASE_URL}/playlistItems"
    videos = []
    page_token = None

    while len(videos) < MAX_PER_CHANNEL:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        for item in data.get("items", []):
            if len(videos) >= MAX_PER_CHANNEL:
                break
            snippet = item["snippet"]
            published_str = snippet.get("publishedAt", "")
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
                "view_count": 0,
                "like_count": 0,
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return videos


def parse_duration(iso_duration):
    import re
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    m = re.match(pattern, iso_duration or '')
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def enrich_videos(videos, min_seconds=300):
    """
    批量查询 contentDetails + statistics，同时：
    - 过滤掉短于 min_seconds 的视频（Shorts）
    - 填充 duration_seconds、view_count、like_count
    """
    if not videos:
        return videos

    ids = [v["id"] for v in videos]
    stats_map = {}

    for i in range(0, len(ids), 50):
        batch = ids[i:i+50]
        try:
            r = requests.get(
                f"{BASE_URL}/videos",
                params={
                    "part": "contentDetails,statistics",
                    "id": ",".join(batch),
                    "key": API_KEY,
                },
                timeout=15
            )
            r.raise_for_status()
            for item in r.json().get("items", []):
                vid_id = item["id"]
                dur = item.get("contentDetails", {}).get("duration", "")
                stats = item.get("statistics", {})
                stats_map[vid_id] = {
                    "duration_seconds": parse_duration(dur),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                }
        except Exception as e:
            print(f"  ⚠️  Stats fetch error: {e}")

    filtered = []
    for v in videos:
        info = stats_map.get(v["id"], {})
        dur = info.get("duration_seconds", 0)
        v["duration_seconds"] = dur
        v["view_count"] = info.get("view_count", 0)
        v["like_count"] = info.get("like_count", 0)
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
    print(f"🚀 Full fetch started at {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"   Max {MAX_PER_CHANNEL} videos per channel, no time limit\n")

    cn_channels = []
    en_channels = []

    for ch in CHANNELS:
        print(f"\nFetching: {ch['name']} ({ch['id']})")
        try:
            playlist_id, channel_thumb = get_channel_uploads_playlist(ch["id"])
            if not playlist_id:
                print(f"  ⚠️  Channel not found, skipping")
                continue

            videos = get_all_videos(playlist_id)
            videos = enrich_videos(videos, min_seconds=300)

            # 默认按发布时间倒序存储
            videos.sort(key=lambda v: v.get("published_at", ""), reverse=True)

            entry = {
                "channel_name": ch["name"],
                "channel_id": ch["id"],
                "channel_thumb": channel_thumb,
                "lang": ch["lang"],
                "videos": videos,
            }

            if ch["lang"] == "cn":
                cn_channels.append(entry)
            else:
                en_channels.append(entry)

            print(f"  ✅  {len(videos)} videos stored for {ch['name']}")

        except Exception as e:
            print(f"  ❌  Error fetching {ch['name']}: {e}")

    all_channels = cn_channels + en_channels
    total = sum(len(ch["videos"]) for ch in all_channels)

    output = {
        "updated_at": now.isoformat(),
        "keep_hours": 0,
        "total_videos": total,
        "channels": all_channels,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/videos.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Full fetch done — {len(cn_channels)} CN + {len(en_channels)} EN channels")
    print(f"   {total} videos total saved to data/videos.json")


if __name__ == "__main__":
    fetch_all()
