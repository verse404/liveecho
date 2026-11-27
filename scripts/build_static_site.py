#!/usr/bin/env python3
"""Builds a zero-server static deployment bundle (dist/) for GitHub Pages & Cloudflare Pages.

Generates strict-CSP static assets (zero inline scripts, zero inline styles, zero backend required)
with daily-refreshed real ShowStart + Songkick concert snapshots.

Usage:
    python3 scripts/build_static_site.py --out-dir dist
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.discovery import discover_songkick_for_artist  # noqa: E402
from app.parser import (  # noqa: E402
    CITY_MAP_NODES,
    CITY_TO_REGION,
    CULTURE_BUREAU_PORTALS,
    PRESET_ARTISTS,
    REGION_LABELS,
    VENUE_GUIDES,
)
import server as liveecho_server  # noqa: E402

SONGKICK_TOP_OVERSEAS_ARTISTS = (
    "Dua Lipa",
    "YOASOBI",
    "Coldplay",
    "Linkin Park",
    "Bruno Mars",
    "ONE OK ROCK",
    "Fujii Kaze",
)

STATIC_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#c83722"/>'
    '<text x="32" y="43" font-size="30" font-weight="bold" fill="#fff" text-anchor="middle">E</text>'
    "</svg>"
)

CLOUDFLARE_HEADERS = f"""/*
  Content-Security-Policy: {STATIC_CSP}; frame-ancestors 'self'
  X-Content-Type-Options: nosniff
  X-Frame-Options: SAMEORIGIN
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()

/static/*
  Cache-Control: public, max-age=3600, must-revalidate

/data/*
  Cache-Control: public, max-age=300, must-revalidate
"""


def build_static_payload(offline_fixture: bool = False) -> dict[str, Any]:
    if offline_fixture:
        live_bundle: dict[str, Any] = {
            "concerts": [
                {
                    "id": 309491,
                    "artist_name": "Demxntia",
                    "artist_category": "overseas",
                    "title": "Demxntia 2026巡演 广州站",
                    "city": "广州",
                    "region": "gba",
                    "venue": "广州疆进酒·OMNI SPACE",
                    "show_time": "2026-12-19 20:00",
                    "price_text": "¥220起",
                    "platform": "秀动",
                    "ticket_url": "https://www.showstart.com/event/309491",
                    "status": "upcoming_drop",
                    "event_kind": "concert",
                    "data_source": "秀动 ShowStart 每日快照",
                    "is_live_verified": True,
                    "ticket_rounds": [],
                    "refund_tiers": [],
                }
            ],
            "fetched_at": "2026-11-27 08:00",
            "sources": ["秀动 ShowStart 每日快照"],
        }
        songkick_snapshots: dict[str, Any] = {}
    else:
        live_bundle = liveecho_server.load_live_website_concerts(force_refresh=True)
        songkick_snapshots = {}
        for artist in SONGKICK_TOP_OVERSEAS_ARTISTS:
            try:
                songkick_snapshots[artist.lower()] = discover_songkick_for_artist(artist)
            except Exception:
                songkick_snapshots[artist.lower()] = {"china_events": [], "global_events": []}

    return {
        "static_mode": True,
        "regions": REGION_LABELS,
        "city_to_region": CITY_TO_REGION,
        "city_map_nodes": CITY_MAP_NODES,
        "venue_guides": VENUE_GUIDES,
        "culture_portals": CULTURE_BUREAU_PORTALS,
        "presets": PRESET_ARTISTS,
        "concerts": live_bundle["concerts"],
        "festival_demo": liveecho_server.build_festival_clash_demo(),
        "live_fetched_at": live_bundle["fetched_at"],
        "live_sources": live_bundle["sources"],
        "songkick_snapshots": songkick_snapshots,
    }


def render_static_index_html(html_src: str) -> str:
    out_html = html_src
    out_html = re.sub(r'\s*<link rel="manifest"[^>]*>\s*', "\n", out_html)

    # Inject strict CSP meta tag + local SVG favicon right after <meta name="viewport"...>
    head_inject = (
        f'  <meta http-equiv="Content-Security-Policy" content="{STATIC_CSP}">\n'
        '  <link rel="icon" type="image/svg+xml" href="./favicon.svg">\n'
    )
    out_html = out_html.replace(
        '<link rel="stylesheet" href="/static/website.css">',
        head_inject + '  <link rel="stylesheet" href="./static/website.css">',
    )

    # Use relative links so the site works on both root domains and GitHub Pages /<repo>/ subpaths
    out_html = out_html.replace('href="/website"', 'href="#site-top"')
    out_html = out_html.replace(
        '<a href="/" id="btn-enter-app" class="site-btn site-btn-primary site-btn-sm">进入个人追踪库</a>',
        '<a href="#watchlist" id="btn-enter-app" class="site-btn site-btn-primary site-btn-sm">★ 本地收藏夹</a>',
    )
    out_html = out_html.replace(
        '<a href="/" id="footer-open-vault" class="site-btn site-btn-primary">打开个人追踪工作台 →</a>',
        '<a href="#site-top" id="footer-open-vault" class="site-btn site-btn-primary">返回顶部继续探索 ↑</a>',
    )
    out_html = out_html.replace(
        "默认零 API Key 开箱即用 · 支持宣纸/黑胶双主题、城市巡演地图与周末月历、高清 PNG 纪念票根导出、.ics 日历闹钟、Bark / Server酱 / Telegram / 飞书 Webhook / SMTP 推送与 Turso 云端同步。",
        "零服务器静态托管版（GitHub Pages / Cloudflare Pages）· 0 Render 配额 · 数据每日自动同步 · 收藏歌手/出发地/主题保存在当前浏览器本地。",
    )
    out_html = out_html.replace(
        '<script nonce="__CSP_NONCE__" src="/static/website.js"></script>',
        '<script src="./static/static-shim.js"></script>\n  <script src="./static/website.js"></script>',
    )
    return out_html


def build_static_site(out_dir: Path, offline_fixture: bool = False) -> dict[str, Any]:
    static_src = ROOT_DIR / "static"
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)

    (out_dir / "static").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)

    html_src = (static_src / "website.html").read_text(encoding="utf-8")
    index_html = render_static_index_html(html_src)

    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    (out_dir / "404.html").write_text(index_html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    (out_dir / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    (out_dir / "_headers").write_text(CLOUDFLARE_HEADERS, encoding="utf-8")

    for asset_name in ("website.css", "website.js", "static-shim.js"):
        shutil.copy2(static_src / asset_name, out_dir / "static" / asset_name)

    payload = build_static_payload(offline_fixture=offline_fixture)
    json_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (out_dir / "data" / "showcase.json").write_bytes(json_bytes)

    total_bytes = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    return {
        "out_dir": str(out_dir),
        "concerts": len(payload["concerts"]),
        "showcase_json_bytes": len(json_bytes),
        "total_bytes": total_bytes,
        "fetched_at": payload["live_fetched_at"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LiveEcho zero-server static site for GitHub/Cloudflare Pages")
    parser.add_argument(
        "--out-dir",
        default=str(ROOT_DIR / "dist"),
        help="Output directory for static site files (default: ./dist)",
    )
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Build using a deterministic offline fixture instead of fetching live feeds (for unit tests).",
    )
    args = parser.parse_args(argv)
    stats = build_static_site(Path(args.out_dir), offline_fixture=args.offline_fixture)
    print(
        f"Built static site in {stats['out_dir']} "
        f"(concerts={stats['concerts']}, showcase_json={stats['showcase_json_bytes']:,} B, "
        f"total={stats['total_bytes']:,} B, fetched_at={stats['fetched_at']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
