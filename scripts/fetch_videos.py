import os
import json
import requests
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────
# 频道配置
# lang: "cn" = 中文频道, "en" = 英文频道
# ─────────────────────────────────────────
CHANNELS = [
    # ── 中文频道 ──
    {"name": "方方土",          "id": "UCjuNibFJ21MiSNpu8LZyV4w", "lang": "cn"},
    {"name": "王志安",          "id": "UCBKDRq35-L8xev4O7ZqBeLg", "lang": "cn"},
    {"name": "马斯库",          "id": "UC-CckeotGQCZigg3nETreCQ", "lang": "cn"},
    {"name": "小Lin说",         "id": "UCilwQlk62k1z7aUEZPOB6yw", "lang": "cn"},
    {"name": "小岛大浪吹",      "id": "UCYPT3wl0MgbOz63ho166KOw", "lang": "cn"},
    {"name": "文昭谈古论今",    "id": "UCtAIPjABiQD3qjlEl1T5VpA", "lang": "cn"},
    {"name": "凤凰卫视Official","id": "UCwAnu01qlnVg1Ai2AbtTMaA", "lang": "cn"},
    {"name": "柴静",            "id": "UC3411UsjUC2t-Xfr1gwIhzg", "lang": "cn"},
    # ── 英文频道 ──
    {"name": "Matt Wolfe",       "id": "UChpleBmo18P08aKCIgti38g", "lang": "en"},
    {"name": "Tina Huang",       "id": "UC2UXDak6o7rBm23k3Vv5dww", "lang": "en"},
    {"name": "Jeff Su",          "id": "UCMtFAi84ehTSYSE9XoHefig",  "lang": "en"},
    {"name": "The AI Advantage", "id": "UCHhYXsLBEVVnbvsq57n1MTQ",  "lang": "en"},
]

KEEP_HOURS = 72          # 保留过去72小时（3天）的视频
MAX_PER_CHANNEL = 20     # 每个频道最多抓取条数

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
            except:
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
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return videos


def fetch_all():
    if not API_KEY:
        raise ValueError("YOUTUBE_API_KEY environment variable not set")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=KEEP_HOURS)
    print(f"Fetching videos published after: {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    cn_channels = []
    en_channels = []

    for ch in CHANNELS:
        print(f"\nFetching: {ch['name']} ({ch['id']})")
        try:
            playlist_id, channel_thumb = get_channel_uploads_playlist(ch["id"])
            if not playlist_id:
                print(f"  ⚠️  Channel not found, skipping")
                continue

            videos = get_videos_within_window(playlist_id, cutoff)

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

            print(f"  ✅  {len(videos)} videos in past {KEEP_HOURS}h")

        except Exception as e:
            print(f"  ❌  Error: {e}")

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
    with open("data/videos.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done — {len(cn_channels)} CN + {len(en_channels)} EN channels, {total} videos total")


if __name__ == "__main__":
    fetch_all()
