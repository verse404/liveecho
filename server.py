#!/usr/bin/env python3
"""LiveEcho (现场回响) v2 — Full China Concert, Festival, Approval & Ticket-Drop Tracker Server.

Run locally:
    python3 -P server.py --host 127.0.0.1 --port 8788
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import datetime
import gzip
import hashlib
import hmac
import http.cookies
import http.server
import json
import logging
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db import SESSION_TTL_SECONDS, Database
from app.discovery import (
    build_platform_search_links,
    discover_live_china_music_feed,
    discover_rss_for_artist,
    discover_showstart_for_artist,
    search_apple_music_artists,
    search_artist_and_concerts_bundle,
)
from app.parser import (
    CITY_MAP_NODES,
    CITY_TO_REGION,
    CULTURE_BUREAU_PORTALS,
    PRESET_ARTISTS,
    REGION_LABELS,
    SHANGHAI_TZ,
    VENUE_GUIDES,
    analyze_festival_groups,
    build_standard_damai_refund_tiers,
    compute_12306_plan,
    compute_stub_wall_stats,
    estimate_weekend_trip_budget,
    get_venue_guide,
    infer_region,
    normalize_city_name,
    parse_concert_announcement,
)
from app.poster_ocr import (
    extract_festival_timetable_via_gemini,
    extract_festival_timetable_via_rapidocr,
    extract_general_text_via_rapidocr,
    extract_poster_text_via_gemini,
    generate_sample_tour_poster_png,
    is_local_ocr_available,
    parse_festival_timetable_lines,
    sanitize_festival_photo_in_memory,
    try_local_tesseract_ocr,
    validate_and_sanitize_poster_upload,
)
from app.reminders import (
    generate_ics_for_concerts,
    run_reminder_check_cycle,
    send_push_or_email_message,
)
from app.security import (
    SecretBox,
    SlidingWindowRateLimiter,
    hash_password,
    load_master_secret,
    validate_outbound_https_url,
    validate_password_strength,
    verify_csrf_token,
    verify_password,
)

STATIC_DIR = (BASE_DIR / "static").resolve()
DATA_DIR = (BASE_DIR / "data").resolve()

MAX_JSON_BODY_BYTES = 131_072  # 128 KB standard JSON cap
MAX_POSTER_JSON_BYTES = 7_500_000  # ~5 MB binary image encoded in base64 JSON
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5]{2,32}$")
UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$")
VALID_STATUSES = {
    "approved_pending",
    "upcoming_drop",
    "announced",
    "waiting_round2",
    "purchased",
    "attended",
    "discovered",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("concert_tracker.server")


class AppContext:
    """Shared application state across HTTP handler threads and background workers."""

    def __init__(self, data_dir: Path | None = None, enable_scheduler: bool = True) -> None:
        self.data_dir = (data_dir or DATA_DIR).resolve()
        self.uploads_dir = (self.data_dir / "uploads").resolve()
        master_secret = load_master_secret(self.data_dir)
        self.secret_box = SecretBox(master_secret)
        self.db = Database(self.data_dir / "concert_tracker.db", self.secret_box)
        self.rate_limiter = SlidingWindowRateLimiter()
        self.allowed_origin_hosts: set[str] = set()
        self._stop_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        if enable_scheduler:
            self._scheduler_thread = threading.Thread(
                target=self._background_loop, name="liveecho-scheduler", daemon=True
            )
            self._scheduler_thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _background_loop(self) -> None:
        last_discovery_run = 0.0
        last_maintenance_run = 0.0
        while not self._stop_event.wait(30.0):
            try:
                run_reminder_check_cycle(self.db)
            except Exception as exc:
                logger.error("Reminder check cycle error: %s", type(exc).__name__)

            now_mono = time.monotonic()
            if (now_mono - last_maintenance_run) >= 3600:
                last_maintenance_run = now_mono
                try:
                    self.db.run_maintenance(uploads_dir=self.uploads_dir)
                    self.rate_limiter.prune()
                except Exception as exc:
                    logger.error("Background maintenance error: %s", type(exc).__name__)

            if (now_mono - last_discovery_run) >= 6 * 3600:
                last_discovery_run = now_mono
                try:
                    self.run_global_auto_discovery()
                except Exception as exc:
                    logger.error("Background discovery cycle error: %s", type(exc).__name__)

    def run_discovery_for_user(self, user_id: int, specific_artist_id: int | None = None) -> dict[str, int]:
        artists = self.db.list_artists(user_id)
        targets = [
            artist
            for artist in artists
            if (specific_artist_id is None and artist.get("auto_discover", True))
            or (specific_artist_id is not None and artist["id"] == specific_artist_id)
        ]
        if not targets:
            return {"artists_checked": 0, "new_concerts": 0}

        existing_keys = {
            c["external_key"] for c in self.db.list_concerts(user_id) if c.get("external_key")
        }

        def _fetch_one(artist: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            found_items: list[dict[str, Any]] = []
            try:
                found_items.extend(discover_showstart_for_artist(artist["name"], artist.get("aliases")))
            except Exception as exc:
                logger.warning("ShowStart discovery failed for artist #%s: %s", artist["id"], type(exc).__name__)

            rss_url = (artist.get("custom_rss_url") or "").strip()
            if rss_url:
                try:
                    found_items.extend(discover_rss_for_artist(rss_url, artist["name"], artist.get("aliases")))
                except Exception as exc:
                    logger.warning("RSS discovery failed for artist #%s: %s", artist["id"], type(exc).__name__)
            return artist, found_items

        added_or_matched = 0
        workers = min(4, len(targets))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            fetched_batches = list(pool.map(_fetch_one, targets))

        for artist, found_items in fetched_batches:
            for item in found_items:
                ext_key = item.get("external_key", "")
                if ext_key and ext_key in existing_keys:
                    continue
                item["artist_id"] = artist["id"]
                self.db.create_concert(user_id, item)
                if ext_key:
                    existing_keys.add(ext_key)
                added_or_matched += 1
            self.db.mark_artist_checked(user_id, artist["id"])

        return {"artists_checked": len(targets), "new_concerts": added_or_matched}

    def run_global_auto_discovery(self) -> None:
        user_ids = {a["user_id"] for a in self.db.list_all_auto_discover_artists()}
        for uid in user_ids:
            self.run_discovery_for_user(uid)


def build_festival_clash_demo(now: datetime.datetime | None = None) -> dict[str, Any]:
    """Isolated interactive demo fixture strictly for the 2-stage Festival Clash Calculator (never mixed into live listings)."""
    ref = now or datetime.datetime.now(SHANGHAI_TZ)
    fest_d1 = (ref + datetime.timedelta(days=18)).strftime("%Y-%m-%d")
    fest_d2 = (ref + datetime.timedelta(days=19)).strftime("%Y-%m-%d")
    return {
        "id": 990001,
        "is_demo_simulator": True,
        "festival_name": "双舞台撞场测算演示（示例排期 · 非实时官宣）",
        "city": "杭州",
        "venue": "户外双舞台音乐节示例",
        "price_text": "示例单日 ¥358 / 两日 ¥628",
        "lineup": [
            {"artist": "万能青年旅店", "stage": "主舞台", "day_date": fest_d1, "set_start": "20:10", "set_end": "21:00"},
            {"artist": "落日飞车", "stage": "副舞台", "day_date": fest_d1, "set_start": "20:30", "set_end": "21:15"},
            {"artist": "蛙池", "stage": "副舞台", "day_date": fest_d1, "set_start": "18:50", "set_end": "19:35"},
            {"artist": "新裤子", "stage": "主舞台", "day_date": fest_d2, "set_start": "20:15", "set_end": "21:05"},
            {"artist": "痛仰乐队", "stage": "副舞台", "day_date": fest_d2, "set_start": "19:20", "set_end": "20:05"},
        ],
    }


def load_live_website_concerts(
    extra_user_concerts: list[dict[str, Any]] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Loads ONLY real live upcoming concerts (ShowStart live China feed + user's own saved Turso concerts).
    Zero fabricated/mock tour dates."""
    live_feed = discover_live_china_music_feed(limit=48, force_refresh=force_refresh)
    items: list[dict[str, Any]] = [copy.deepcopy(c) for c in (live_feed.get("items") or [])]
    seen_keys = {
        f"{c.get('city', '')}|{(c.get('show_time') or '')[:10]}|{(c.get('title') or '')[:20]}"
        for c in items
    }

    for uc in extra_user_concerts or []:
        if uc.get("status") == "attended":
            continue
        k = f"{uc.get('city', '')}|{(uc.get('show_time') or '')[:10]}|{(uc.get('title') or '')[:20]}"
        if k in seen_keys:
            continue
        seen_keys.add(k)
        c_copy = copy.deepcopy(uc)
        c_copy["data_source"] = "我的 Turso 个人追踪库"
        c_copy["is_live_verified"] = True
        if "artist_category" not in c_copy:
            c_copy["artist_category"] = "cn"
        items.append(c_copy)

    items.sort(key=lambda c: c.get("show_time") or "9999-99-99")
    return {
        "concerts": items,
        "fetched_at": live_feed.get("fetched_at") or datetime.datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M"),
        "sources": live_feed.get("sources") or ["秀动 ShowStart 实时在售", "Songkick 全球排期实时核验"],
    }


def build_website_showcase_concerts(now: datetime.datetime | None = None) -> list[dict[str, Any]]:
    """Backwards-compatible helper returning only real live concerts (never fabricated dates)."""
    return load_live_website_concerts()["concerts"]


def enrich_artist_bundle_with_presales(
    query_str: str,
    bundle: dict[str, Any],
    extra_concerts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merges ONLY real live discoveries (ShowStart + Songkick China/HK/Macau) and user's own tracked concerts.
    Never injects synthetic/fabricated tour stops."""
    prof = bundle.get("primary_profile") or {"name": query_str, "aliases": []}
    raw_tokens = [query_str, str(prof.get("name") or "")] + list(prof.get("aliases") or [])
    for p in PRESET_ARTISTS:
        p_all = [p["name"]] + list(p.get("aliases") or [])
        if any(rt and rt.strip().lower() in [x.lower() for x in p_all] for rt in raw_tokens):
            raw_tokens.extend(p_all)

    match_tokens = {t.strip().lower() for t in raw_tokens if t and len(t.strip()) >= 2}

    pool: list[dict[str, Any]] = list(bundle.get("concerts") or [])
    seen_keys = {f"{c.get('city', '')}|{(c.get('show_time') or '')[:10]}|{(c.get('title') or '')[:16]}" for c in pool}

    for uc in extra_concerts or []:
        hay = f"{uc.get('artist_name', '')} {uc.get('title', '')}".lower()
        if any(tok in hay for tok in match_tokens):
            dedup_k = f"{uc.get('city', '')}|{(uc.get('show_time') or '')[:10]}|{(uc.get('title') or '')[:16]}"
            if dedup_k not in seen_keys:
                seen_keys.add(dedup_k)
                uc_copy = copy.deepcopy(uc)
                uc_copy["data_source"] = uc_copy.get("data_source") or "我的个人追踪库"
                pool.append(uc_copy)

    bundle["concerts"] = pool

    presale_alerts: list[dict[str, Any]] = []
    for c in pool:
        if c.get("status") == "attended":
            continue
        city = c.get("city", "")
        region_label = REGION_LABELS.get(c.get("region", "other"), "")
        rounds = c.get("ticket_rounds") or []
        refunds = [rf for rf in (c.get("refund_tiers") or []) if rf.get("expect_return_drop")]
        src_label = c.get("data_source") or ("秀动 ShowStart 实时" if c.get("source_type") == "showstart" else c.get("platform", "实时数据源"))

        if rounds:
            for r in rounds:
                presale_alerts.append(
                    {
                        "concert_id": c.get("id", 0),
                        "artist_name": c.get("artist_name", ""),
                        "city": city,
                        "region_label": region_label,
                        "title": c.get("title", ""),
                        "venue": c.get("venue", ""),
                        "show_time": c.get("show_time", ""),
                        "presale_label": r.get("round_label", "门票预售"),
                        "presale_time": r.get("sale_time", ""),
                        "platform": r.get("platform") or c.get("platform", "大麦"),
                        "price_text": c.get("price_text", ""),
                        "ticket_url": r.get("booking_url") or c.get("ticket_url", ""),
                        "data_source": src_label,
                        "alert_kind": "presale",
                    }
                )
        elif refunds:
            rf0 = refunds[0]
            presale_alerts.append(
                {
                    "concert_id": c.get("id", 0),
                    "artist_name": c.get("artist_name", ""),
                    "city": city,
                    "region_label": region_label,
                    "title": c.get("title", ""),
                    "venue": c.get("venue", ""),
                    "show_time": c.get("show_time", ""),
                    "presale_label": rf0.get("tier_label", "退票回流放票"),
                    "presale_time": rf0.get("cutoff_time", ""),
                    "platform": c.get("platform", "大麦"),
                    "price_text": c.get("price_text", ""),
                    "ticket_url": c.get("ticket_url", ""),
                    "data_source": src_label,
                    "alert_kind": "return_drop",
                }
            )
        elif c.get("status") == "approved_pending":
            presale_alerts.append(
                {
                    "concert_id": c.get("id", 0),
                    "artist_name": c.get("artist_name", ""),
                    "city": city,
                    "region_label": region_label,
                    "title": c.get("title", ""),
                    "venue": c.get("venue", ""),
                    "show_time": c.get("show_time", ""),
                    "presale_label": f"文旅已过审（{c.get('approval_doc_no') or '待官宣预售'}）",
                    "presale_time": "",
                    "platform": c.get("approval_source") or "省市文旅局",
                    "price_text": c.get("price_text", ""),
                    "ticket_url": c.get("ticket_url", ""),
                    "data_source": src_label,
                    "alert_kind": "approval_early",
                }
            )
        else:
            presale_alerts.append(
                {
                    "concert_id": c.get("id", 0),
                    "artist_name": c.get("artist_name", ""),
                    "city": city,
                    "region_label": region_label,
                    "title": c.get("title", ""),
                    "venue": c.get("venue", ""),
                    "show_time": c.get("show_time", ""),
                    "presale_label": "官方在售 / 实时排期",
                    "presale_time": "",
                    "platform": c.get("platform", "秀动"),
                    "price_text": c.get("price_text", ""),
                    "ticket_url": c.get("ticket_url", ""),
                    "data_source": src_label,
                    "alert_kind": "discovered",
                }
            )

    presale_alerts.sort(key=lambda a: (0 if a.get("presale_time") else 1, a.get("presale_time") or a.get("show_time") or "9999"))
    bundle["upcoming_presales"] = presale_alerts
    bundle["upcoming_cities"] = list(dict.fromkeys(a["city"] for a in presale_alerts if a.get("city")))
    return bundle


def seed_starter_concerts(db: Database, user_id: int) -> None:
    """Seeds sample concerts demonstrating all 6 China concert-going features (clearly tagged [示例])."""
    now = datetime.datetime.now(SHANGHAI_TZ)
    drop_soon = (now + datetime.timedelta(hours=18)).replace(hour=12, minute=18, second=0, microsecond=0)
    if drop_soon <= now:
        drop_soon += datetime.timedelta(days=1)

    show1_dt = (now + datetime.timedelta(days=24)).replace(hour=19, minute=30)
    fest_day1 = (now + datetime.timedelta(days=19)).strftime("%Y-%m-%d")
    fest_day2 = (now + datetime.timedelta(days=20)).strftime("%Y-%m-%d")

    samples: list[dict[str, Any]] = [
        {
            "artist_name": "万能青年旅店",
            "title": "[示例] 万能青年旅店 2026 剧场特别专场（上海站）",
            "city": "上海",
            "region": "jzh",
            "venue": "梅赛德斯-奔驰文化中心",
            "show_time": show1_dt.strftime("%Y-%m-%d %H:%M"),
            "price_text": "¥380-980",
            "platform": "大麦",
            "ticket_url": "https://www.damai.cn/",
            "status": "upcoming_drop",
            "checklist_want": True,
            "checklist_realname": False,
            "checklist_alarm": True,
            "source_type": "manual",
            "notes": "演示：抢票倒计时 + 阶梯退票截止线 & 回流票狙击预警",
            "ticket_rounds": [
                {
                    "round_label": "一开",
                    "sale_time": drop_soon.strftime("%Y-%m-%d %H:%M"),
                    "platform": "大麦",
                    "booking_url": "https://www.damai.cn/",
                }
            ],
            "refund_tiers": build_standard_damai_refund_tiers(
                drop_soon.strftime("%Y-%m-%d %H:%M"),
                show1_dt.strftime("%Y-%m-%d %H:%M"),
            ),
        },
        {
            "artist_name": "周杰伦",
            "title": "[示例] 周杰伦 2027 嘉年华世界巡回演唱会（南京站）",
            "city": "南京",
            "region": "jzh",
            "venue": "南京奥体中心体育场",
            "show_time": (now + datetime.timedelta(days=52)).replace(hour=19, minute=30).strftime("%Y-%m-%d %H:%M"),
            "price_text": "¥580-2000",
            "platform": "文旅局公示",
            "ticket_url": "https://wlt.jiangsu.gov.cn/",
            "status": "approved_pending",
            "approval_doc_no": "苏文旅许〔2026〕0819号",
            "approval_source": "江苏省文化和旅游厅",
            "hotel_booked": True,
            "rail_booked": False,
            "source_type": "manual",
            "notes": "演示：省文旅局审批早鸟雷达（未官宣先锁可退酒店）+ 跨城 12306 高铁开售日历联动",
            "ticket_rounds": [],
            "refund_tiers": [],
        },
        {
            "artist_name": "万能青年旅店 / 痛仰乐队 / 声音玩具",
            "title": "[示例] 2026 长三角秋日草莓音乐节",
            "city": "杭州",
            "region": "jzh",
            "venue": "杭州大运河杭钢公园",
            "show_time": f"{fest_day1} 13:30",
            "price_text": "单日 ¥358 / 两日通票 ¥628",
            "platform": "秀动",
            "ticket_url": "https://www.showstart.com/",
            "status": "upcoming_drop",
            "event_kind": "festival",
            "festival_name": "[示例] 2026 长三角秋日草莓音乐节",
            "lineup": [
                {"artist": "万能青年旅店", "stage": "草莓舞台", "day_date": fest_day1, "set_start": "20:10", "set_end": "20:55"},
                {"artist": "声音玩具", "stage": "爱舞台", "day_date": fest_day1, "set_start": "20:25", "set_end": "21:10"},
                {"artist": "痛仰乐队", "stage": "草莓舞台", "day_date": fest_day2, "set_start": "20:20", "set_end": "21:05"},
            ],
            "ticket_rounds": [
                {
                    "round_label": "早鸟一开",
                    "sale_time": (now + datetime.timedelta(days=2)).replace(hour=11, minute=18).strftime("%Y-%m-%d %H:%M"),
                    "platform": "秀动",
                    "booking_url": "https://www.showstart.com/",
                }
            ],
            "refund_tiers": [],
        },
        {
            "artist_name": "陶喆",
            "title": "[示例] 陶喆 Soul Power II 世界巡回演唱会（成都站）",
            "city": "成都",
            "region": "cy",
            "venue": "东安湖体育公园多功能体育馆",
            "show_time": (now + datetime.timedelta(days=16)).replace(hour=19, minute=30).strftime("%Y-%m-%d %H:%M"),
            "price_text": "¥380-1380",
            "platform": "猫眼",
            "ticket_url": "https://show.maoyan.com/",
            "status": "purchased",
            "seat_note": "内场 A2区 8排 12座（强实名带身份证！）",
            "actual_paid_yuan": 1080,
            "checklist_want": True,
            "checklist_realname": True,
            "checklist_alarm": True,
            "source_type": "manual",
            "ticket_rounds": [],
            "refund_tiers": [
                {
                    "tier_label": "20%手续费退票截止",
                    "cutoff_time": (now + datetime.timedelta(days=9)).replace(hour=12, minute=0).strftime("%Y-%m-%d %H:%M"),
                    "fee_percent": 20,
                    "expect_return_drop": True,
                }
            ],
        },
        {
            "artist_name": "草东没有派对",
            "title": "[示例] 草东没有派对 专场现场（深圳站）",
            "city": "深圳",
            "region": "gba",
            "venue": "B10现场",
            "show_time": (now - datetime.timedelta(days=18)).replace(hour=20, minute=0).strftime("%Y-%m-%d %H:%M"),
            "price_text": "¥280",
            "platform": "秀动",
            "ticket_url": "https://www.showstart.com/",
            "status": "attended",
            "seat_note": "站席中前区偏左",
            "actual_paid_yuan": 280,
            "venue_rating": 5,
            "seat_view_note": "B10现场声场干净通透，调音台前方三米听感最佳，空调给力。",
            "setlist_note": "开场《丑》，安可连唱《大风吹》+《烂泥》+《山海》，全场大合唱久久不散。",
            "source_type": "manual",
            "ticket_rounds": [],
            "refund_tiers": [],
        },
    ]
    for s in samples:
        db.create_concert(user_id, s)


class ConcertTrackerRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler enforcing method allow-lists, CSP nonces, CSRF, rate limits, and auth."""

    context: AppContext
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        raw_line = fmt % args
        scrubbed = re.sub(r"token=[^&\s\"']+", "token=[REDACTED]", raw_line)
        logger.info("%s - %s", self.client_address[0], scrubbed)

    def _is_tls(self) -> bool:
        forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        return forwarded_proto == "https" or os.getenv("CONCERT_TRACKER_TLS", "") == "1"

    def _accepts_gzip(self) -> bool:
        enc = (self.headers.get("Accept-Encoding") or "").lower()
        return "gzip" in enc

    def _maybe_gzip(self, raw_bytes: bytes) -> tuple[bytes, bool]:
        if len(raw_bytes) >= 512 and self._accepts_gzip():
            return gzip.compress(raw_bytes, compresslevel=6), True
        return raw_bytes, False

    def _client_key(self) -> str:
        return self.client_address[0] or "local"

    def _write_security_headers(self, nonce: str = "", cache_control: str = "no-store") -> None:
        script_policy = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
        csp = (
            f"default-src 'self'; "
            f"script-src {script_policy}; "
            f"style-src 'self'; "
            f"img-src 'self' data: blob:; "
            f"font-src 'self'; "
            f"connect-src 'self'; "
            f"manifest-src 'self'; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"frame-ancestors 'self'"
        )
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Cache-Control", cache_control)

    def _send_json(
        self,
        status_code: int,
        payload: dict[str, Any],
        extra_headers: list[tuple[str, str]] | None = None,
        cache_control: str = "no-store",
    ) -> None:
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        body, is_gz = self._maybe_gzip(raw_body)
        extra_list = list(extra_headers or [])
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if not any(k.lower() == "vary" for k, _ in extra_list):
            self.send_header("Vary", "Accept-Encoding")
        if is_gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self._write_security_headers(cache_control=cache_control)
        for k, v in extra_list:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_method_not_allowed(self) -> None:
        self._send_json(
            405,
            {"error": "Method not allowed. Only GET, POST, and HEAD are permitted."},
            extra_headers=[("Allow", "GET, POST, HEAD")],
        )

    def do_PUT(self) -> None:  # noqa: N802
        self._send_method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._send_method_not_allowed()

    def do_TRACE(self) -> None:  # noqa: N802
        self._send_method_not_allowed()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_method_not_allowed()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # ---------------- Cookie & CSRF Helpers ----------------

    def _parse_cookies(self) -> dict[str, str]:
        raw_cookie = self.headers.get("Cookie") or ""
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(raw_cookie)
        except http.cookies.CookieError:
            return {}
        return {k: morsel.value for k, morsel in jar.items()}

    def _build_cookie_header(self, base_name: str, value: str, max_age: int, http_only: bool = True) -> str:
        # Enforce __Host- cookie prefix and Secure flag under TLS (Render / reverse proxy / CONCERT_TRACKER_TLS=1);
        # conditional only for plain-HTTP local development so localhost browsers retain cookies.
        is_tls = self._is_tls()
        cookie_name = f"__Host-{base_name}" if is_tls else base_name
        parts = [
            f"{cookie_name}={value}",
            "Path=/",
            f"Max-Age={max_age}",
            "SameSite=Lax",
        ]
        if http_only:
            parts.append("HttpOnly")
        if is_tls:
            parts.append("Secure")
        return "; ".join(parts)

    def _get_session(self) -> dict[str, Any] | None:
        cookies = self._parse_cookies()
        token = cookies.get("__Host-liveecho_session") or cookies.get("liveecho_session") or ""
        return self.context.db.validate_session(token)

    def _get_or_make_preauth_csrf(self) -> tuple[str, list[tuple[str, str]]]:
        cookies = self._parse_cookies()
        existing = cookies.get("__Host-liveecho_preauth_csrf") or cookies.get("liveecho_preauth_csrf") or ""
        if len(existing) >= 32:
            return existing, []
        fresh = secrets.token_urlsafe(32)
        hdr = self._build_cookie_header("liveecho_preauth_csrf", fresh, 86400, http_only=True)
        return fresh, [("Set-Cookie", hdr)]

    def _check_same_origin(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        parsed = urllib.parse.urlsplit(origin)
        origin_host = (parsed.netloc or "").strip().lower()
        if not origin_host:
            return False

        allowed_hosts = {
            (self.headers.get("Host") or "").strip().lower(),
            (self.headers.get("X-Forwarded-Host") or "").strip().lower(),
        }
        allowed_hosts.update(getattr(self.context, "allowed_origin_hosts", set()))
        if origin_host in allowed_hosts:
            return True
        return False

    def _read_json_body(self, max_bytes: int = MAX_JSON_BODY_BYTES) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._send_json(400, {"error": "Invalid Content-Length header."})
            return None
        if length <= 0 or length > max_bytes:
            self._send_json(413, {"error": "Request payload empty or exceeds allowed size limit."})
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Malformed JSON payload."})
            return None
        if not isinstance(data, dict):
            self._send_json(400, {"error": "JSON payload must be an object."})
            return None
        return data

    # ---------------- GET Routing ----------------

    def do_GET(self) -> None:  # noqa: N802
        parsed_url = urllib.parse.urlsplit(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        allowed, retry_after = self.context.rate_limiter.allow(f"get:{self._client_key()}", 240, 60.0)
        if not allowed:
            self._send_json(429, {"error": "Too many requests. Please slow down."}, [("Retry-After", str(retry_after))])
            return

        if path == "/" or path == "/index.html":
            self._serve_html_template("index.html")
            return

        if path in ("/website", "/website/", "/site", "/website.html"):
            self._serve_html_template("website.html")
            return

        if path == "/favicon.ico":
            svg_icon = (
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                b'<rect width="64" height="64" rx="12" fill="#c83722"/>'
                b'<text x="32" y="43" font-size="30" font-weight="bold" fill="#fff" text-anchor="middle">E</text>'
                b"</svg>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(svg_icon)))
            self._write_security_headers(cache_control="public, max-age=86400")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(svg_icon)
            return

        if path.startswith("/static/"):
            self._serve_static_file(path[len("/static/") :])
            return

        if path == "/api/healthz":
            self._send_json(200, {"ok": True, "status": "healthy", "storage": self.context.db.backend_mode})
            return

        if path == "/api/auth/status":
            session = self._get_session()
            if session:
                self._send_json(
                    200,
                    {
                        "authenticated": True,
                        "needs_setup": False,
                        "username": session["username"],
                        "csrf_token": session["csrf_token"],
                        "preferred_region": session["preferred_region"],
                        "preferred_cities": session["preferred_cities"],
                        "home_city": session["home_city"],
                        "calendar_feed_path": f"/api/calendar/feed.ics?token={session['calendar_token']}",
                    },
                )
            else:
                pre_csrf, extra_hdrs = self._get_or_make_preauth_csrf()
                self._send_json(
                    200,
                    {
                        "authenticated": False,
                        "needs_setup": self.context.db.count_users() == 0,
                        "csrf_token": pre_csrf,
                        "presets": PRESET_ARTISTS,
                        "regions": REGION_LABELS,
                    },
                    extra_headers=extra_hdrs,
                )
            return

        if path == "/api/calendar/feed.ics":
            # TODO(security): WebCal subscription clients require a URL token; token is 256-bit random,
            # read-only, scrubbed from access logs, rate-limited, and rotatable in 1 click by the user.
            ok_cal, retry_cal = self.context.rate_limiter.allow(f"cal:{self._client_key()}", 30, 60.0)
            if not ok_cal:
                self._send_json(429, {"error": "Rate limit exceeded."}, [("Retry-After", str(retry_cal))])
                return
            token = (query.get("token") or [""])[0].strip()
            user = self.context.db.get_user_by_calendar_token(token)
            if not user:
                self._send_json(401, {"error": "Invalid or revoked calendar token."})
                return
            concerts = [
                c
                for c in self.context.db.list_concerts(user["id"])
                if c.get("status") not in ("discovered",)
            ]
            ics_body = generate_ics_for_concerts(
                concerts, home_city=user.get("home_city", "上海")
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="liveecho-concerts.ics"')
            self.send_header("Content-Length", str(len(ics_body)))
            self._write_security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(ics_body)
            return

        if path == "/api/public/artist-preview":
            ok_pub, retry_pub = self.context.rate_limiter.allow(f"pub_artist:{self._client_key()}", 15, 60.0)
            if not ok_pub:
                self._send_json(429, {"error": "搜索过于频繁，请稍后再试。"}, [("Retry-After", str(retry_pub))])
                return
            q = (query.get("q") or [""])[0].strip()
            if not q or len(q) > 50:
                self._send_json(400, {"error": "请输入有效的歌手或乐队名称。"})
                return
            bundle = search_artist_and_concerts_bundle(q)
            session = self._get_session()
            user_concerts = self.context.db.list_concerts(session["user_id"]) if session else None
            bundle = enrich_artist_bundle_with_presales(q, bundle, extra_concerts=user_concerts)
            self._send_json(200, bundle)
            return

        if path == "/api/public/showcase":
            ok_sc, retry_sc = self.context.rate_limiter.allow(f"pub_showcase:{self._client_key()}", 60, 60.0)
            if not ok_sc:
                self._send_json(429, {"error": "请求过于频繁，请稍后再试。"}, [("Retry-After", str(retry_sc))])
                return
            req_home = normalize_city_name((query.get("home_city") or ["上海"])[0])[:16] or "上海"
            session = self._get_session()
            if session:
                csrf_tok = session["csrf_token"]
                extra_hdrs: list[tuple[str, str]] = []
                followed_names = [a["name"] for a in self.context.db.list_artists(session["user_id"])]
                user_concerts = self.context.db.list_concerts(session["user_id"])
            else:
                csrf_tok, extra_hdrs = self._get_or_make_preauth_csrf()
                followed_names = []
                user_concerts = []

            want_refresh = (query.get("refresh") or ["0"])[0] == "1"
            if want_refresh:
                ok_rf, retry_rf = self.context.rate_limiter.allow(f"pub_refresh:{self._client_key()}", 4, 60.0)
                if not ok_rf:
                    want_refresh = False

            live_bundle = load_live_website_concerts(
                extra_user_concerts=user_concerts,
                force_refresh=want_refresh,
            )
            showcase_concerts = live_bundle["concerts"]
            for sc in showcase_concerts:
                sc["rail_plan"] = compute_12306_plan(req_home, sc)
                sc["trip_estimate"] = estimate_weekend_trip_budget(req_home, sc)
                sc["venue_guide"] = get_venue_guide(sc.get("venue", ""), sc.get("title", ""))

            env_vision_ready = bool((os.getenv("GEMINI_API_KEY") or os.getenv("LIVE_ECHO_VISION_API_KEY") or "").strip())
            user_vision_ready = False
            if session:
                try:
                    u_set = self.context.db.get_notification_settings_decrypted(session["user_id"])
                    user_vision_ready = bool((u_set.get("vision_api_key") or "").strip())
                except Exception:
                    user_vision_ready = False

            local_ocr_ready = is_local_ocr_available()
            etag_seed = json.dumps(
                [
                    live_bundle["fetched_at"],
                    req_home,
                    bool(session),
                    session["username"] if session else "",
                    csrf_tok,
                    followed_names,
                    [
                        (c.get("id"), c.get("status"), c.get("show_time"), c.get("title"), c.get("updated_at", ""))
                        for c in showcase_concerts
                    ],
                    local_ocr_ready,
                    env_vision_ready or user_vision_ready,
                ],
                ensure_ascii=False,
            ).encode("utf-8")
            showcase_etag = f'W/"{hashlib.sha256(etag_seed).hexdigest()[:20]}"'
            inm = (self.headers.get("If-None-Match") or "").strip()
            inm_matches = bool(inm) and (
                inm == "*" or any(tok.strip() == showcase_etag for tok in inm.split(","))
            )
            if not want_refresh and not extra_hdrs and inm_matches:
                self.send_response(304)
                self.send_header("ETag", showcase_etag)
                self.send_header("Vary", "Cookie, Accept-Encoding")
                self._write_security_headers(cache_control="private, max-age=0, must-revalidate")
                self.end_headers()
                return

            resp_hdrs = list(extra_hdrs) + [
                ("ETag", showcase_etag),
                ("Vary", "Cookie, Accept-Encoding"),
            ]
            self._send_json(
                200,
                {
                    "authenticated": bool(session),
                    "username": session["username"] if session else "",
                    "followed_artists": followed_names,
                    "csrf_token": csrf_tok,
                    "home_city": req_home,
                    "regions": REGION_LABELS,
                    "city_map_nodes": CITY_MAP_NODES,
                    "venue_guides": VENUE_GUIDES,
                    "culture_portals": CULTURE_BUREAU_PORTALS,
                    "presets": PRESET_ARTISTS,
                    "concerts": showcase_concerts,
                    "festival_demo": build_festival_clash_demo(),
                    "local_ocr_available": local_ocr_ready,
                    "vision_ocr_available": env_vision_ready or user_vision_ready or local_ocr_ready,
                    "live_fetched_at": live_bundle["fetched_at"],
                    "live_sources": live_bundle["sources"],
                    "server_shanghai_time": datetime.datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                },
                extra_headers=resp_hdrs,
                cache_control="private, max-age=0, must-revalidate",
            )
            return

        if path == "/api/public/showcase-ics":
            ok_ics, retry_ics = self.context.rate_limiter.allow(f"pub_ics:{self._client_key()}", 30, 60.0)
            if not ok_ics:
                self._send_json(429, {"error": "导出过于频繁，请稍后再试。"}, [("Retry-After", str(retry_ics))])
                return
            req_home = normalize_city_name((query.get("home_city") or ["上海"])[0])[:16] or "上海"
            cid_param = (query.get("id") or ["all"])[0].strip()
            artists_param = (query.get("artists") or [""])[0].strip()
            showcase_concerts = build_website_showcase_concerts()
            if artists_param:
                wanted = {a.strip().lower() for a in artists_param.split(",") if a.strip()}
                selected = [
                    c
                    for c in showcase_concerts
                    if any(w in f"{c['artist_name']} {c['title']}".lower() for w in wanted)
                ]
                if not selected:
                    selected = showcase_concerts
                fname = "liveecho-favorite-artists-presale.ics"
            elif cid_param != "all":
                try:
                    target_id = int(cid_param)
                except ValueError:
                    self._send_json(400, {"error": "Invalid showcase concert ID."})
                    return
                selected = [c for c in showcase_concerts if c["id"] == target_id]
                if not selected:
                    self._send_json(404, {"error": "Showcase concert not found."})
                    return
                fname = f"liveecho-showcase-{target_id}.ics"
            else:
                selected = showcase_concerts
                fname = "liveecho-china-concerts-showcase.ics"

            ics_bytes = generate_ics_for_concerts(selected, home_city=req_home).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(ics_bytes)))
            self._write_security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(ics_bytes)
            return

        if not path.startswith("/api/"):
            self._send_json(404, {"error": "Not found."})
            return

        session = self._get_session()
        if not session:
            self._send_json(401, {"error": "Authentication required."})
            return
        user_id = session["user_id"]
        home_city = session.get("home_city", "上海")

        if path == "/api/bootstrap":
            artists = self.context.db.list_artists(user_id)
            for a in artists:
                a["search_links"] = build_platform_search_links(a["name"])
            concerts = self.context.db.list_concerts(user_id)
            for c in concerts:
                c["rail_plan"] = compute_12306_plan(home_city, c)
            festival_groups = analyze_festival_groups(concerts, artists)
            stub_stats = compute_stub_wall_stats(concerts)
            notif = self.context.db.get_notification_settings_masked(user_id)
            self._send_json(
                200,
                {
                    "user": {
                        "username": session["username"],
                        "preferred_region": session["preferred_region"],
                        "preferred_cities": session["preferred_cities"],
                        "home_city": home_city,
                        "calendar_feed_path": f"/api/calendar/feed.ics?token={session['calendar_token']}",
                    },
                    "csrf_token": session["csrf_token"],
                    "regions": REGION_LABELS,
                    "city_to_region": CITY_TO_REGION,
                    "culture_portals": CULTURE_BUREAU_PORTALS,
                    "presets": PRESET_ARTISTS,
                    "artists": artists,
                    "concerts": concerts,
                    "festival_groups": festival_groups,
                    "stub_wall_stats": stub_stats,
                    "notification_settings": notif,
                    "server_shanghai_time": datetime.datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            return

        if path == "/api/artists/live-search-bundle":
            ok_b, retry_b = self.context.rate_limiter.allow(f"artist_bundle:{user_id}", 20, 60.0)
            if not ok_b:
                self._send_json(429, {"error": "搜索过于频繁，请稍后再试"}, [("Retry-After", str(retry_b))])
                return
            q = (query.get("q") or [""])[0].strip()
            if not q or len(q) > 60:
                self._send_json(400, {"error": "请输入歌手或乐队名称。"})
                return
            bundle = search_artist_and_concerts_bundle(q)
            user_concerts = self.context.db.list_concerts(user_id)
            bundle = enrich_artist_bundle_with_presales(q, bundle, extra_concerts=user_concerts)
            self._send_json(200, bundle)
            return

        if path == "/api/artists/search-online":
            ok_s, retry_s = self.context.rate_limiter.allow(f"artist_search:{user_id}", 20, 60.0)
            if not ok_s:
                self._send_json(429, {"error": "搜索过于频繁，请稍后再试"}, [("Retry-After", str(retry_s))])
                return
            q = (query.get("q") or [""])[0].strip()
            if len(q) > 60:
                self._send_json(400, {"error": "Search query too long."})
                return
            try:
                results = search_apple_music_artists(q)
            except Exception:
                results = []
            self._send_json(200, {"results": results})
            return

        if path == "/api/calendar/concert.ics":
            cid_str = (query.get("id") or ["0"])[0]
            try:
                cid = int(cid_str)
            except ValueError:
                self._send_json(400, {"error": "Invalid concert ID."})
                return
            concert = self.context.db.get_concert(user_id, cid)
            if not concert:
                self._send_json(404, {"error": "Concert not found."})
                return
            ics_bytes = generate_ics_for_concerts(
                [concert],
                cal_name=f"现场回响 · {concert['artist_name']}",
                home_city=home_city,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="concert-{cid}.ics"')
            self.send_header("Content-Length", str(len(ics_bytes)))
            self._write_security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(ics_bytes)
            return

        if path == "/api/posters/download":
            poster_uuid = (query.get("uuid") or [""])[0].strip()
            if not UUID_HEX_RE.fullmatch(poster_uuid):
                self._send_json(400, {"error": "Invalid poster ID."})
                return
            rec = self.context.db.get_uploaded_poster(user_id, poster_uuid)
            if not rec:
                self._send_json(404, {"error": "Poster not found."})
                return
            safe_file = os.path.basename(rec["stored_filename"])
            resolved = (self.context.uploads_dir / safe_file).resolve()
            img_bytes: bytes | None = None
            if str(resolved).startswith(str(self.context.uploads_dir) + os.sep) and resolved.is_file():
                img_bytes = resolved.read_bytes()
            else:
                img_bytes = self.context.db.get_uploaded_poster_bytes(user_id, poster_uuid)
            if not img_bytes:
                self._send_json(404, {"error": "Poster file missing."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Disposition", f'attachment; filename="poster-{poster_uuid[:8]}.png"')
            self.send_header("Content-Length", str(len(img_bytes)))
            self._write_security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(img_bytes)
            return

        if path == "/api/backup/export":
            ok_exp, retry_exp = self.context.rate_limiter.allow(f"backup_exp:{user_id}", 10, 60.0)
            if not ok_exp:
                self._send_json(429, {"error": "导出过于频繁，请稍后再试。"}, [("Retry-After", str(retry_exp))])
                return
            vault = self.context.db.export_user_vault(user_id)
            raw_bytes = json.dumps(vault, ensure_ascii=False, indent=2).encode("utf-8")
            out_bytes, is_gz = self._maybe_gzip(raw_bytes)
            date_tag = datetime.datetime.now(SHANGHAI_TZ).strftime("%Y%m%d")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="liveecho-vault-{date_tag}.json"')
            self.send_header("Vary", "Accept-Encoding")
            if is_gz:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(out_bytes)))
            self._write_security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(out_bytes)
            return

        self._send_json(404, {"error": "Not found."})

    # ---------------- POST Routing ----------------

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_same_origin():
            self._send_json(403, {"error": "Cross-origin state-changing requests are forbidden."})
            return

        parsed_url = urllib.parse.urlsplit(self.path)
        path = parsed_url.path
        provided_csrf = (self.headers.get("X-CSRF-Token") or "").strip()

        if path == "/api/cron/tick":
            # Non-cookie machine-to-machine scheduler endpoint authenticated exclusively via Bearer secret.
            ok_cron, retry_cron = self.context.rate_limiter.allow(f"cron_tick:{self._client_key()}", 12, 60.0)
            if not ok_cron:
                self._send_json(429, {"error": "Cron rate limit exceeded."}, [("Retry-After", str(retry_cron))])
                return
            expected_cron = os.getenv("CRON_SECRET", "").strip()
            if len(expected_cron) < 32:
                self._send_json(503, {"error": "CRON_SECRET is not configured on this server."})
                return
            auth_hdr = (self.headers.get("Authorization") or "").strip()
            provided_secret = auth_hdr[7:].strip() if auth_hdr.startswith("Bearer ") else ""
            if not provided_secret or not hmac.compare_digest(expected_cron, provided_secret):
                self._send_json(401, {"error": "Unauthorized cron request."})
                return
            cron_body = self._read_json_body()
            if cron_body is None:
                return
            sent_count = run_reminder_check_cycle(self.context.db, lookback_minutes=22.0)
            discovery_ran = False
            if cron_body.get("run_discovery"):
                self.context.run_global_auto_discovery()
                discovery_ran = True
            maint = self.context.db.run_maintenance(uploads_dir=self.context.uploads_dir)
            self._send_json(
                200,
                {
                    "ok": True,
                    "reminders_sent": sent_count,
                    "discovery_ran": discovery_ran,
                    "maintenance": maint,
                },
            )
            return

        if path in (
            "/api/auth/register",
            "/api/auth/login",
            "/api/public/parse-preview",
            "/api/public/parse-ics",
            "/api/public/parse-festival-photo",
        ):
            if path == "/api/public/parse-festival-photo":
                ok_fp, retry_fp = self.context.rate_limiter.allow(f"pub_fest_photo:{self._client_key()}", 8, 60.0)
                if not ok_fp:
                    self._send_json(
                        429,
                        {"error": "图片识别过于频繁，请 1 分钟后再试。"},
                        [("Retry-After", str(retry_fp))],
                    )
                    return
            else:
                ok_auth, retry_auth = self.context.rate_limiter.allow(f"preauth_post:{self._client_key()}", 25, 60.0)
                if not ok_auth:
                    self._send_json(
                        429,
                        {"error": "请求过于频繁，请1分钟后再试。"},
                        [("Retry-After", str(retry_auth))],
                    )
                    return

            cookies = self._parse_cookies()
            expected_pre_csrf = (
                cookies.get("__Host-liveecho_preauth_csrf") or cookies.get("liveecho_preauth_csrf") or ""
            )
            active_sess = self._get_session()
            csrf_valid = verify_csrf_token(expected_pre_csrf, provided_csrf) or (
                active_sess is not None and verify_csrf_token(active_sess["csrf_token"], provided_csrf)
            )
            if not csrf_valid:
                self._send_json(403, {"error": "CSRF 校验失败，请刷新页面后重试。"})
                return

            body = self._read_json_body(
                max_bytes=MAX_POSTER_JSON_BYTES if path == "/api/public/parse-festival-photo" else 128 * 1024
            )
            if body is None:
                return

            if path == "/api/public/parse-festival-photo":
                self._handle_public_festival_photo(active_sess, body)
                return

            if path == "/api/public/parse-preview":
                raw_text = str(body.get("text") or "")[:12_000]
                req_home = normalize_city_name(str(body.get("home_city") or "上海"))[:16] or "上海"
                parsed = parse_concert_announcement(raw_text, known_artists=PRESET_ARTISTS)
                for item in parsed.get("items") or []:
                    item["rail_plan"] = compute_12306_plan(req_home, item)
                    item["trip_estimate"] = estimate_weekend_trip_budget(req_home, item)
                    item["venue_guide"] = get_venue_guide(item.get("venue", ""), item.get("title", ""))
                self._send_json(200, parsed)
                return

            if path == "/api/public/parse-ics":
                raw_text = str(body.get("text") or "")[:12_000]
                req_home = normalize_city_name(str(body.get("home_city") or "上海"))[:16] or "上海"
                parsed = parse_concert_announcement(raw_text, known_artists=PRESET_ARTISTS)
                items = parsed.get("items") or []
                if not items:
                    self._send_json(400, {"error": "未从文案中识别到可导出的演出日程，请检查演出日期与艺人名称。"})
                    return
                ics_bytes = generate_ics_for_concerts(items, home_city=req_home).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/calendar; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="liveecho-parsed-concert.ics"')
                self.send_header("Content-Length", str(len(ics_bytes)))
                self._write_security_headers()
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(ics_bytes)
                return

            if path == "/api/auth/register":
                self._handle_register(body)
            else:
                self._handle_login(body)
            return

        session = self._get_session()
        if not session:
            self._send_json(401, {"error": "登录已过期，请重新登录。"})
            return

        if not verify_csrf_token(session["csrf_token"], provided_csrf):
            self._send_json(403, {"error": "无效的 CSRF 令牌，请求已被拒绝。"})
            return

        user_id = session["user_id"]
        ok_post, retry_post = self.context.rate_limiter.allow(f"post:{user_id}", 80, 60.0)
        if not ok_post:
            self._send_json(429, {"error": "操作过于频繁，请稍后再试。"}, [("Retry-After", str(retry_post))])
            return

        if path == "/api/auth/logout":
            self.context.db.invalidate_all_user_sessions(user_id)
            clear_headers = [
                ("Set-Cookie", "liveecho_session=; Path=/; Max-Age=0; SameSite=Lax; HttpOnly"),
                ("Set-Cookie", "liveecho_preauth_csrf=; Path=/; Max-Age=0; SameSite=Lax; HttpOnly"),
            ]
            if self._is_tls():
                clear_headers.append(
                    ("Set-Cookie", "__Host-liveecho_session=; Path=/; Max-Age=0; SameSite=Lax; HttpOnly; Secure")
                )
                clear_headers.append(
                    ("Set-Cookie", "__Host-liveecho_preauth_csrf=; Path=/; Max-Age=0; SameSite=Lax; HttpOnly; Secure")
                )
            self._send_json(200, {"ok": True}, extra_headers=clear_headers)
            return

        if path == "/api/backup/import":
            ok_imp, retry_imp = self.context.rate_limiter.allow(f"backup_imp:{user_id}", 5, 60.0)
            if not ok_imp:
                self._send_json(429, {"error": "备份导入过于频繁，请稍后再试。"}, [("Retry-After", str(retry_imp))])
                return
            body = self._read_json_body(max_bytes=2 * 1024 * 1024)
            if body is None:
                return
            self._handle_backup_import(user_id, body)
            return

        if path == "/api/posters/upload":
            ok_up, retry_up = self.context.rate_limiter.allow(f"poster_up:{user_id}", 10, 60.0)
            if not ok_up:
                self._send_json(429, {"error": "海报上传过于频繁，请稍后再试。"}, [("Retry-After", str(retry_up))])
                return
            body = self._read_json_body(max_bytes=MAX_POSTER_JSON_BYTES)
            if body is None:
                return
            self._handle_poster_upload(user_id, body)
            return

        body = self._read_json_body()
        if body is None:
            return

        if path == "/api/preferences/update":
            region = (body.get("preferred_region") or session["preferred_region"] or "all").strip()
            if region not in REGION_LABELS:
                self._send_json(400, {"error": "无效的区域筛选值。"})
                return
            raw_cities = body.get("preferred_cities", session["preferred_cities"])
            if not isinstance(raw_cities, list):
                self._send_json(400, {"error": "城市列表格式错误。"})
                return
            cities = [normalize_city_name(str(c))[:16] for c in raw_cities if str(c).strip()][:20]
            home_city = normalize_city_name(str(body.get("home_city") or session.get("home_city") or "上海"))[:16] or "上海"
            self.context.db.update_user_preferences(user_id, region, cities, home_city=home_city)
            self._send_json(
                200,
                {"ok": True, "preferred_region": region, "preferred_cities": cities, "home_city": home_city},
            )
            return

        if path == "/api/calendar/rotate-token":
            new_tok = self.context.db.rotate_calendar_token(user_id)
            self._send_json(200, {"ok": True, "calendar_feed_path": f"/api/calendar/feed.ics?token={new_tok}"})
            return

        if path == "/api/artists/upsert":
            self._handle_artist_upsert(user_id, body)
            return

        if path == "/api/artists/delete":
            aid = int(body.get("id") or 0)
            deleted = self.context.db.delete_artist(user_id, aid)
            self._send_json(200 if deleted else 404, {"ok": deleted})
            return

        if path == "/api/concerts/parse":
            raw_text = str(body.get("text") or "")[:12_000]
            known = self.context.db.list_artists(user_id)
            parsed = parse_concert_announcement(raw_text, known_artists=known)
            self._send_json(200, parsed)
            return

        if path == "/api/concerts/generate-refund-tiers":
            first_sale = str(body.get("first_sale_time") or "").strip()
            show_time = str(body.get("show_time") or "").strip()
            tiers = build_standard_damai_refund_tiers(first_sale, show_time)
            self._send_json(200, {"refund_tiers": tiers})
            return

        if path == "/api/concerts/create":
            self._handle_concert_create_or_batch(user_id, body)
            return

        if path == "/api/concerts/update":
            self._handle_concert_update(user_id, body)
            return

        if path == "/api/concerts/quick-patch":
            self._handle_concert_quick_patch(user_id, body)
            return

        if path == "/api/concerts/delete":
            cid = int(body.get("id") or 0)
            deleted = self.context.db.delete_concert(user_id, cid, uploads_dir=self.context.uploads_dir)
            self._send_json(200 if deleted else 404, {"ok": deleted})
            return

        if path == "/api/discover/run":
            ok_disc, retry_disc = self.context.rate_limiter.allow(f"discover:{user_id}", 8, 60.0)
            if not ok_disc:
                self._send_json(
                    429,
                    {"error": "巡演雷达扫描过于频繁，请稍候再试。"},
                    [("Retry-After", str(retry_disc))],
                )
                return
            specific_id = int(body["artist_id"]) if body.get("artist_id") else None
            stats = self.context.run_discovery_for_user(user_id, specific_artist_id=specific_id)
            self._send_json(200, {"ok": True, **stats})
            return

        if path == "/api/settings/notifications":
            self._handle_notification_settings_save(user_id, body)
            return

        if path == "/api/notifications/test":
            ok_test, retry_test = self.context.rate_limiter.allow(f"notif_test:{user_id}", 5, 60.0)
            if not ok_test:
                self._send_json(429, {"error": "测试推送过于频繁，请稍后再试。"}, [("Retry-After", str(retry_test))])
                return
            channel = (body.get("channel") or "").strip() or None
            settings = self.context.db.get_notification_settings_decrypted(user_id)
            outcomes = send_push_or_email_message(
                settings,
                subject="现场回响 · 抢票/回流/12306 提醒测试",
                body="恭喜！你的提醒通道已连通。抢票前、退票回流窗口及跨城 12306 开售前将准时向你发送强提醒。",
                target_url="https://www.showstart.com/",
                only_channel=channel,
            )
            if not outcomes:
                self._send_json(400, {"error": "尚未配置该推送通道或密钥为空，请先保存设置后再测试。"})
                return
            self._send_json(200, {"ok": True, "outcomes": outcomes})
            return

        self._send_json(404, {"error": "Unknown API endpoint."})

    # ---------------- Business Handlers ----------------

    def _handle_register(self, body: dict[str, Any]) -> None:
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        if not USERNAME_RE.fullmatch(username):
            self._send_json(400, {"error": "用户名需为 2-32 位中英文、数字、下划线或连字符。"})
            return
        pw_err = validate_password_strength(password)
        if pw_err:
            self._send_json(400, {"error": pw_err})
            return
        if self.context.db.get_user_by_username(username):
            self._send_json(409, {"error": "该用户名已存在，请直接登录或更换名称。"})
            return

        pref_region = str(body.get("preferred_region") or "all").strip()
        if pref_region not in REGION_LABELS:
            pref_region = "all"
        home_city = normalize_city_name(str(body.get("home_city") or "上海"))[:16] or "上海"

        pw_hash = hash_password(password)
        user_id = self.context.db.create_user(
            username, pw_hash, preferred_region=pref_region, home_city=home_city
        )

        selected_names = body.get("starter_artists") or []
        preset_map = {p["name"]: p for p in PRESET_ARTISTS}
        if isinstance(selected_names, list):
            for s_name in selected_names[:20]:
                clean_name = str(s_name).strip()[:60]
                if not clean_name:
                    continue
                if clean_name in preset_map:
                    p = preset_map[clean_name]
                    self.context.db.upsert_artist(
                        user_id,
                        name=p["name"],
                        aliases=p["aliases"],
                        genre=p["genre"],
                        region_origin=p["region_origin"],
                        auto_discover=True,
                    )
                else:
                    self.context.db.upsert_artist(user_id, name=clean_name, auto_discover=True)

        custom_artists = body.get("custom_artist_objects") or []
        if isinstance(custom_artists, list):
            for ca in custom_artists[:12]:
                if not isinstance(ca, dict) or not str(ca.get("name") or "").strip():
                    continue
                aid = self.context.db.upsert_artist(
                    user_id,
                    name=str(ca["name"]).strip()[:60],
                    aliases=[str(x).strip()[:40] for x in (ca.get("aliases") or [])[:6] if str(x).strip()],
                    genre=str(ca.get("genre") or "").strip()[:40],
                    region_origin=str(ca.get("region_origin") or "").strip()[:24],
                    auto_discover=True,
                )
                for disc_c in (ca.get("discovered_concerts") or [])[:10]:
                    if isinstance(disc_c, dict):
                        clean_c, err_c = self._sanitize_concert_payload(disc_c)
                        if clean_c and not err_c:
                            clean_c["artist_id"] = aid
                            clean_c["external_key"] = str(disc_c.get("external_key") or "")[:120]
                            self.context.db.create_concert(user_id, clean_c)

        if body.get("include_demo_concerts", True):
            seed_starter_concerts(self.context.db, user_id)

        raw_token, csrf_token = self.context.db.create_session(user_id)
        cookie_hdr = self._build_cookie_header("liveecho_session", raw_token, SESSION_TTL_SECONDS, http_only=True)
        self._send_json(
            201,
            {"ok": True, "username": username, "csrf_token": csrf_token},
            extra_headers=[("Set-Cookie", cookie_hdr)],
        )

    def _handle_login(self, body: dict[str, Any]) -> None:
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        user = self.context.db.get_user_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            self._send_json(401, {"error": "用户名或密码不正确。"})
            return

        raw_token, csrf_token = self.context.db.create_session(int(user["id"]))
        cookie_hdr = self._build_cookie_header("liveecho_session", raw_token, SESSION_TTL_SECONDS, http_only=True)
        self._send_json(
            200,
            {"ok": True, "username": user["username"], "csrf_token": csrf_token},
            extra_headers=[("Set-Cookie", cookie_hdr)],
        )

    def _handle_public_festival_photo(self, session: dict[str, Any] | None, body: dict[str, Any]) -> None:
        """Sanitizes an uploaded festival timetable photo purely in memory and extracts stage slots via Vision/OCR."""
        filename = str(body.get("filename") or "timetable.png")
        b64_str = str(body.get("image_base64") or "").strip()
        if "," in b64_str and b64_str.startswith("data:"):
            b64_str = b64_str.split(",", 1)[1]
        if not b64_str:
            self._send_json(400, {"error": "请先选择或粘贴音乐节时刻表图片。"})
            return
        try:
            raw_bytes = base64.b64decode(b64_str, validate=True)
        except Exception:
            self._send_json(400, {"error": "图片 Base64 数据解码失败，请重新选择图片。"})
            return

        try:
            sanitized = sanitize_festival_photo_in_memory(filename=filename, raw_bytes=raw_bytes)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        mode = str(body.get("mode") or "festival").strip().lower()
        req_home = normalize_city_name(str(body.get("home_city") or "上海"))[:16] or "上海"
        festival_name = str(body.get("festival_name") or "").strip()[:80]
        default_date = str(body.get("default_date") or "").strip()[:10]
        raw_known = body.get("known_bands") or []
        known_bands = [str(b).strip()[:40] for b in raw_known[:40] if str(b).strip()] if isinstance(raw_known, list) else []

        # Resolve Vision API Key securely (logged-in user encrypted setting -> server env -> ephemeral per-request key)
        vision_key = ""
        if session:
            try:
                u_settings = self.context.db.get_notification_settings_decrypted(session["user_id"])
                vision_key = (u_settings.get("vision_api_key") or "").strip()
            except Exception:
                vision_key = ""
        if not vision_key:
            vision_key = (os.getenv("GEMINI_API_KEY") or os.getenv("LIVE_ECHO_VISION_API_KEY") or "").strip()
        if not vision_key:
            req_key = str(body.get("vision_api_key") or "").strip()
            if 10 <= len(req_key) <= 200:
                vision_key = req_key

        extracted_text = ""
        ocr_mode = "preview_only"
        warning = ""

        if vision_key:
            try:
                if mode == "announcement":
                    extracted_text = extract_poster_text_via_gemini(sanitized["sanitized_bytes"], vision_key)
                else:
                    extracted_text = extract_festival_timetable_via_gemini(
                        sanitized["sanitized_bytes"],
                        vision_key,
                        festival_name=festival_name,
                        default_date=default_date,
                        known_bands=known_bands,
                    )
                ocr_mode = "gemini_vision"
            except ValueError as exc:
                ocr_mode = "vision_error"
                warning = str(exc)
            except Exception:
                ocr_mode = "vision_error"
                warning = "在线 Vision OCR 请求失败，已为你保留安全净化后的海报对照预览。"

        if not extracted_text:
            rapid_txt = (
                extract_general_text_via_rapidocr(sanitized["sanitized_bytes"])
                if mode == "announcement"
                else extract_festival_timetable_via_rapidocr(
                    sanitized["sanitized_bytes"],
                    default_date=default_date,
                    known_bands=known_bands,
                )
            )
            if rapid_txt:
                extracted_text = rapid_txt
                ocr_mode = "local_rapidocr"
                warning = ""

        if not extracted_text:
            tess_txt = try_local_tesseract_ocr(sanitized["sanitized_bytes"])
            if tess_txt:
                extracted_text = tess_txt
                ocr_mode = "local_tesseract"

        if not extracted_text and sanitized.get("embedded_schedule_hint"):
            extracted_text = sanitized["embedded_schedule_hint"]
            ocr_mode = "embedded_schedule"

        preview_data_url = "data:image/png;base64," + base64.b64encode(sanitized["sanitized_bytes"]).decode("ascii")

        if mode == "announcement":
            parsed = (
                parse_concert_announcement(extracted_text, known_artists=PRESET_ARTISTS)
                if extracted_text
                else {"items": [], "summary": ""}
            )
            for item in parsed.get("items") or []:
                item["rail_plan"] = compute_12306_plan(req_home, item)
                item["trip_estimate"] = estimate_weekend_trip_budget(req_home, item)
                item["venue_guide"] = get_venue_guide(item.get("venue", ""), item.get("title", ""))
            self._send_json(
                200,
                {
                    "ok": True,
                    "width": sanitized["width"],
                    "height": sanitized["height"],
                    "ocr_mode": ocr_mode,
                    "extracted_text": extracted_text[:12000],
                    "parsed": parsed,
                    "warning": warning,
                    "preview_data_url": preview_data_url,
                },
            )
            return

        slots = parse_festival_timetable_lines(extracted_text, default_date=default_date) if extracted_text else []
        if ocr_mode in ("gemini_vision", "local_rapidocr", "local_tesseract") and not slots:
            engine_lbl = "本地免费中文 OCR" if ocr_mode == "local_rapidocr" else "识图引擎"
            warning = (
                f"{engine_lbl}已完成识别，但未在照片中检测到明确的分舞台起止时间（例如只有阵容名单或字体过于花哨）；"
                "已把识别到的文字填入下方文本框，你可对照上方高清预览微调或补录。"
            )
        elif ocr_mode == "preview_only" and not warning:
            warning = (
                "照片已完成 EXIF 隐私剥离与安全重编码，可点击上方预览图放大对照录入；"
                "如需一键自动识图，请在「个人追踪库」或下方临时输入框填入 Gemini Vision API Key（或安装本地 RapidOCR）。"
            )

        self._send_json(
            200,
            {
                "ok": True,
                "width": sanitized["width"],
                "height": sanitized["height"],
                "ocr_mode": ocr_mode,
                "vision_configured": bool(vision_key),
                "extracted_text": extracted_text[:8000],
                "slots": slots,
                "warning": warning,
                "preview_data_url": preview_data_url,
            },
        )

    def _handle_poster_upload(self, user_id: int, body: dict[str, Any]) -> None:
        use_sample = bool(body.get("use_sample_poster"))
        if use_sample:
            raw_bytes = generate_sample_tour_poster_png()
            filename = "sample-oys-tour-poster.png"
        else:
            filename = str(body.get("filename") or "poster.png")
            b64_str = str(body.get("image_base64") or "").strip()
            if "," in b64_str and b64_str.startswith("data:"):
                b64_str = b64_str.split(",", 1)[1]
            try:
                raw_bytes = base64.b64decode(b64_str, validate=True)
            except Exception:
                self._send_json(400, {"error": "Base64 图像数据解码失败。"})
                return

        try:
            saved = validate_and_sanitize_poster_upload(
                filename=filename,
                raw_bytes=raw_bytes,
                uploads_dir=self.context.uploads_dir,
            )
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        self.context.db.record_uploaded_poster(
            user_id,
            poster_uuid=saved["poster_uuid"],
            stored_filename=saved["stored_filename"],
            original_name=saved["original_name"],
            width=saved["width"],
            height=saved["height"],
            image_blob=saved["sanitized_bytes"],
        )

        settings = self.context.db.get_notification_settings_decrypted(user_id)
        vision_key = settings.get("vision_api_key", "")
        extracted_text = ""
        ocr_mode = "none"

        if vision_key and not use_sample:
            try:
                extracted_text = extract_poster_text_via_gemini(saved["sanitized_bytes"], vision_key)
                ocr_mode = "gemini_vision"
            except Exception as exc:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "poster_uuid": saved["poster_uuid"],
                        "ocr_mode": "vision_error",
                        "warning": f"海报已安全净化保存，但在线识图失败：{exc}",
                        "extracted_text": "",
                        "parsed": {"items": [], "summary": ""},
                    },
                )
                return
        elif saved["embedded_schedule_hint"]:
            extracted_text = saved["embedded_schedule_hint"]
            ocr_mode = "sample_poster_ocr"
        else:
            rapid_general = extract_general_text_via_rapidocr(saved["sanitized_bytes"])
            if rapid_general:
                extracted_text = rapid_general
                ocr_mode = "local_rapidocr"

        known = self.context.db.list_artists(user_id)
        parsed = parse_concert_announcement(extracted_text, known_artists=known) if extracted_text else {"items": [], "summary": ""}
        for it in parsed.get("items") or []:
            it["poster_uuid"] = saved["poster_uuid"]

        preview_data_url = (
            "data:image/png;base64," + base64.b64encode(saved["sanitized_bytes"]).decode("ascii")
            if use_sample
            else ""
        )

        self._send_json(
            200,
            {
                "ok": True,
                "poster_uuid": saved["poster_uuid"],
                "width": saved["width"],
                "height": saved["height"],
                "ocr_mode": ocr_mode,
                "vision_configured": bool(vision_key),
                "extracted_text": extracted_text,
                "parsed": parsed,
                "sample_preview_data_url": preview_data_url,
            },
        )

    def _handle_artist_upsert(self, user_id: int, body: dict[str, Any]) -> None:
        name = str(body.get("name") or "").strip()[:60]
        if not name:
            self._send_json(400, {"error": "请输入乐队或歌手名称。"})
            return
        raw_aliases = body.get("aliases") or []
        if isinstance(raw_aliases, str):
            aliases = [x.strip()[:40] for x in re.split(r"[,，/、]", raw_aliases) if x.strip()]
        elif isinstance(raw_aliases, list):
            aliases = [str(x).strip()[:40] for x in raw_aliases if str(x).strip()]
        else:
            aliases = []

        custom_rss = str(body.get("custom_rss_url") or "").strip()[:300]
        if custom_rss:
            try:
                validate_outbound_https_url(custom_rss)
            except ValueError as exc:
                self._send_json(400, {"error": f"RSS 地址校验未通过：{exc}"})
                return

        apple_url = str(body.get("apple_music_url") or "").strip()[:300]
        if apple_url and not apple_url.startswith("https://"):
            apple_url = ""

        aid = self.context.db.upsert_artist(
            user_id,
            name=name,
            aliases=aliases[:10],
            genre=str(body.get("genre") or "").strip()[:40],
            region_origin=str(body.get("region_origin") or "").strip()[:24],
            apple_music_url=apple_url,
            auto_discover=bool(body.get("auto_discover", True)),
            custom_rss_url=custom_rss,
        )
        disc_stats = {"new_concerts": 0}
        if body.get("scan_immediately", True):
            disc_stats = self.context.run_discovery_for_user(user_id, specific_artist_id=aid)
        self._send_json(200, {"ok": True, "artist_id": aid, **disc_stats})

    def _sanitize_concert_payload(self, item: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        artist_name = str(item.get("artist_name") or "").strip()[:80]
        title = str(item.get("title") or "").strip()[:140]
        city = normalize_city_name(str(item.get("city") or ""))[:24]
        show_time = str(item.get("show_time") or "").strip().replace("T", " ")[:16]
        if not artist_name or not city or not show_time:
            return None, "请填写完整的艺人、城市与演出时间。"
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?", show_time):
            return None, "演出时间格式需为 YYYY-MM-DD HH:MM。"
        if len(show_time) == 10:
            show_time = f"{show_time} 19:30"

        region = str(item.get("region") or "").strip()
        if region not in REGION_LABELS or region == "all":
            region = infer_region(city)

        status = str(item.get("status") or "upcoming_drop").strip()
        if status not in VALID_STATUSES:
            status = "upcoming_drop"

        event_kind = "festival" if str(item.get("event_kind") or "") == "festival" else "concert"
        ticket_url = str(item.get("ticket_url") or "").strip()[:400]
        if ticket_url and not ticket_url.startswith("https://"):
            return None, "购票链接必须使用 https:// 协议。"

        poster_uuid = str(item.get("poster_uuid") or "").strip()
        if poster_uuid and not UUID_HEX_RE.fullmatch(poster_uuid):
            poster_uuid = ""

        clean_rounds: list[dict[str, str]] = []
        for tr in item.get("ticket_rounds") or []:
            if not isinstance(tr, dict):
                continue
            st = str(tr.get("sale_time") or "").strip().replace("T", " ")[:16]
            if not st:
                continue
            if len(st) == 10 and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", st):
                st = f"{st} 12:18"
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}", st):
                return None, f"抢票时间格式无效：{st}"
            b_url = str(tr.get("booking_url") or ticket_url).strip()[:400]
            if b_url and not b_url.startswith("https://"):
                b_url = ""
            clean_rounds.append(
                {
                    "round_label": str(tr.get("round_label") or "一开").strip()[:20],
                    "sale_time": st,
                    "platform": str(tr.get("platform") or item.get("platform") or "大麦").strip()[:20],
                    "booking_url": b_url,
                }
            )

        clean_refunds: list[dict[str, Any]] = []
        for rf in item.get("refund_tiers") or []:
            if not isinstance(rf, dict):
                continue
            ct = str(rf.get("cutoff_time") or "").strip().replace("T", " ")[:16]
            if not ct:
                continue
            if len(ct) == 10 and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", ct):
                ct = f"{ct} 12:00"
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}", ct):
                return None, f"退票截止时间格式无效：{ct}"
            clean_refunds.append(
                {
                    "tier_label": str(rf.get("tier_label") or "无条件退截止").strip()[:32],
                    "cutoff_time": ct,
                    "fee_percent": max(0, min(100, int(rf.get("fee_percent") or 0))),
                    "expect_return_drop": bool(rf.get("expect_return_drop", True)),
                }
            )

        clean_lineup: list[dict[str, str]] = []
        for sl in item.get("lineup") or []:
            if not isinstance(sl, dict) or not str(sl.get("artist") or "").strip():
                continue
            clean_lineup.append(
                {
                    "artist": str(sl.get("artist") or "").strip()[:32],
                    "stage": str(sl.get("stage") or "主舞台").strip()[:20],
                    "day_date": str(sl.get("day_date") or show_time[:10]).strip()[:10],
                    "set_start": str(sl.get("set_start") or "").strip()[:5],
                    "set_end": str(sl.get("set_end") or "").strip()[:5],
                }
            )

        try:
            paid_yuan = max(0, min(100_000, int(item.get("actual_paid_yuan") or 0)))
        except (TypeError, ValueError):
            paid_yuan = 0

        try:
            venue_rating = max(0, min(5, int(item.get("venue_rating") or 0)))
        except (TypeError, ValueError):
            venue_rating = 0

        return (
            {
                "artist_name": artist_name,
                "title": title or f"{artist_name}（{city}站）",
                "city": city,
                "region": region,
                "venue": str(item.get("venue") or "").strip()[:80],
                "show_time": show_time,
                "price_text": str(item.get("price_text") or "").strip()[:40],
                "platform": str(item.get("platform") or "大麦").strip()[:24],
                "ticket_url": ticket_url,
                "status": status,
                "seat_note": str(item.get("seat_note") or "").strip()[:120],
                "checklist_want": bool(item.get("checklist_want", False)),
                "checklist_realname": bool(item.get("checklist_realname", False)),
                "checklist_alarm": bool(item.get("checklist_alarm", False)),
                "hotel_booked": bool(item.get("hotel_booked", False)),
                "rail_booked": bool(item.get("rail_booked", False)),
                "event_kind": event_kind,
                "festival_name": str(item.get("festival_name") or (title if event_kind == "festival" else "")).strip()[:80],
                "lineup": clean_lineup[:30],
                "approval_doc_no": str(item.get("approval_doc_no") or "").strip()[:48],
                "approval_source": str(item.get("approval_source") or "").strip()[:48],
                "poster_uuid": poster_uuid,
                "actual_paid_yuan": paid_yuan,
                "venue_rating": venue_rating,
                "seat_view_note": str(item.get("seat_view_note") or "").strip()[:400],
                "setlist_note": str(item.get("setlist_note") or "").strip()[:500],
                "source_type": str(item.get("source_type") or "manual").strip()[:20],
                "notes": str(item.get("notes") or "").strip()[:500],
                "ticket_rounds": clean_rounds[:6],
                "refund_tiers": clean_refunds[:6],
            },
            None,
        )

    def _handle_concert_create_or_batch(self, user_id: int, body: dict[str, Any]) -> None:
        raw_items = body.get("items") if isinstance(body.get("items"), list) else [body]
        created_ids: list[int] = []
        for raw_item in raw_items[:20]:
            if not isinstance(raw_item, dict):
                continue
            clean, err = self._sanitize_concert_payload(raw_item)
            if err or not clean:
                self._send_json(400, {"error": err or "场次数据校验失败"})
                return
            if body.get("auto_follow_artist", True) and clean["event_kind"] != "festival":
                for single_art in re.split(r"[/、]", clean["artist_name"])[:3]:
                    s_art = single_art.strip()
                    if s_art:
                        self.context.db.upsert_artist(user_id, name=s_art)
            cid = self.context.db.create_concert(user_id, clean)
            created_ids.append(cid)
        self._send_json(201, {"ok": True, "ids": created_ids})

    def _handle_concert_update(self, user_id: int, body: dict[str, Any]) -> None:
        cid = int(body.get("id") or 0)
        clean, err = self._sanitize_concert_payload(body)
        if err or not clean:
            self._send_json(400, {"error": err or "场次数据校验失败"})
            return
        updated = self.context.db.update_concert(user_id, cid, clean)
        self._send_json(200 if updated else 404, {"ok": updated})

    def _handle_concert_quick_patch(self, user_id: int, body: dict[str, Any]) -> None:
        cid = int(body.get("id") or 0)
        updates: dict[str, Any] = {}
        if "status" in body and body["status"] is not None:
            st = str(body["status"]).strip()
            if st not in VALID_STATUSES:
                self._send_json(400, {"error": "无效的演出状态。"})
                return
            updates["status"] = st
        for bcol in ("checklist_want", "checklist_realname", "checklist_alarm", "hotel_booked", "rail_booked"):
            if bcol in body and body[bcol] is not None:
                updates[bcol] = bool(body[bcol])
        for scol, limit in (("seat_note", 120), ("seat_view_note", 400), ("setlist_note", 500)):
            if scol in body and body[scol] is not None:
                updates[scol] = str(body[scol]).strip()[:limit]
        if "actual_paid_yuan" in body and body["actual_paid_yuan"] is not None:
            updates["actual_paid_yuan"] = max(0, min(100_000, int(body["actual_paid_yuan"])))
        if "venue_rating" in body and body["venue_rating"] is not None:
            updates["venue_rating"] = max(0, min(5, int(body["venue_rating"])))

        ok = self.context.db.patch_concert_quick_state(user_id, cid, updates)
        self._send_json(200 if ok else 404, {"ok": ok})

    def _handle_notification_settings_save(self, user_id: int, body: dict[str, Any]) -> None:
        for url_field in ("bark_url", "webhook_url"):
            val = str(body.get(url_field) or "").strip()
            if val:
                try:
                    validate_outbound_https_url(val)
                except ValueError as exc:
                    self._send_json(400, {"error": f"{url_field} 安全检查未通过：{exc}"})
                    return

        self.context.db.update_notification_settings(user_id, body)
        masked = self.context.db.get_notification_settings_masked(user_id)
        self._send_json(200, {"ok": True, "notification_settings": masked})

    def _handle_backup_import(self, user_id: int, body: dict[str, Any]) -> None:
        raw_artists = body.get("artists")
        raw_concerts = body.get("concerts")
        if not isinstance(raw_artists, list) and not isinstance(raw_concerts, list):
            self._send_json(400, {"error": "无效的备份文件结构：缺少 artists 或 concerts 数组。"})
            return

        prefs = body.get("preferences")
        if isinstance(prefs, dict):
            p_reg = str(prefs.get("preferred_region") or "all").strip()
            if p_reg not in REGION_LABELS:
                p_reg = "all"
            p_cities = [
                normalize_city_name(str(c))[:16]
                for c in (prefs.get("preferred_cities") or [])
                if str(c).strip()
            ][:20]
            p_home = normalize_city_name(str(prefs.get("home_city") or "上海"))[:16] or "上海"
            self.context.db.update_user_preferences(user_id, p_reg, p_cities, home_city=p_home)

        artists_imported = 0
        for a in (raw_artists or [])[:100]:
            if not isinstance(a, dict) or not str(a.get("name") or "").strip():
                continue
            rss_u = str(a.get("custom_rss_url") or "").strip()[:300]
            if rss_u:
                try:
                    validate_outbound_https_url(rss_u)
                except ValueError:
                    rss_u = ""
            apple_u = str(a.get("apple_music_url") or "").strip()[:300]
            if apple_u and not apple_u.startswith("https://"):
                apple_u = ""
            self.context.db.upsert_artist(
                user_id,
                name=str(a["name"]).strip()[:60],
                aliases=[str(x).strip()[:40] for x in (a.get("aliases") or [])[:10] if str(x).strip()],
                genre=str(a.get("genre") or "").strip()[:40],
                region_origin=str(a.get("region_origin") or "").strip()[:24],
                apple_music_url=apple_u,
                auto_discover=bool(a.get("auto_discover", True)),
                custom_rss_url=rss_u,
            )
            artists_imported += 1

        concerts_imported = 0
        for c in (raw_concerts or [])[:300]:
            if not isinstance(c, dict):
                continue
            clean_c, err_c = self._sanitize_concert_payload(c)
            if clean_c and not err_c:
                clean_c["poster_uuid"] = ""  # Do not bind arbitrary cross-vault poster UUIDs
                self.context.db.create_concert(user_id, clean_c)
                concerts_imported += 1

        self._send_json(
            200,
            {"ok": True, "artists_imported": artists_imported, "concerts_imported": concerts_imported},
        )

    # ---------------- HTML & Static Asset Serving ----------------

    def _serve_html_template(self, template_filename: str) -> None:
        safe_name = os.path.basename(template_filename)
        html_file = (STATIC_DIR / safe_name).resolve()
        if not str(html_file).startswith(str(STATIC_DIR) + os.sep) or not html_file.is_file():
            self._send_json(500, {"error": "Frontend HTML template missing."})
            return
        nonce = secrets.token_urlsafe(18)
        _, extra_hdrs = self._get_or_make_preauth_csrf()
        html_content = html_file.read_text(encoding="utf-8").replace("__CSP_NONCE__", nonce)
        raw_encoded = html_content.encode("utf-8")
        encoded, is_gz = self._maybe_gzip(raw_encoded)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Vary", "Accept-Encoding")
        if is_gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(encoded)))
        self._write_security_headers(nonce=nonce, cache_control="no-store")
        for k, v in extra_hdrs:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    def _serve_static_file(self, rel_path: str) -> None:
        clean_name = os.path.normpath(rel_path).lstrip("/\\")
        resolved = (STATIC_DIR / clean_name).resolve()
        if not str(resolved).startswith(str(STATIC_DIR) + os.sep) or not resolved.is_file():
            self._send_json(404, {"error": "Static file not found."})
            return

        st = resolved.stat()
        etag = f'W/"{st.st_mtime_ns:x}-{st.st_size:x}"'
        inm = (self.headers.get("If-None-Match") or "").strip()
        if inm and inm == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self._write_security_headers(cache_control="public, max-age=60")
            self.end_headers()
            return

        raw_content = resolved.read_bytes()
        content, is_gz = self._maybe_gzip(raw_content)
        mime_type, _ = mimetypes.guess_type(str(resolved))
        if resolved.suffix == ".js":
            mime_type = "application/javascript; charset=utf-8"
        elif resolved.suffix == ".css":
            mime_type = "text/css; charset=utf-8"
        elif resolved.suffix == ".json":
            mime_type = "application/manifest+json; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("ETag", etag)
        self.send_header("Vary", "Accept-Encoding")
        if is_gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(content)))
        self._write_security_headers(cache_control="public, max-age=60")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)


class ReusableThreadingHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True


class ThreadedIPv6HTTPServer(ReusableThreadingHTTPServer):
    address_family = socket.AF_INET6


def create_http_servers(
    host: str,
    port: int,
    context: AppContext,
    extra_host: str = "",
) -> list[http.server.ThreadingHTTPServer]:
    """Creates primary HTTP server(s), preferring loopback by default unless configured for containers."""

    class BoundHandler(ConcertTrackerRequestHandler):
        pass

    BoundHandler.context = context

    servers: list[http.server.ThreadingHTTPServer] = []
    if host in ("127.0.0.1", "localhost"):
        v4_srv = ReusableThreadingHTTPServer(("127.0.0.1", port), BoundHandler)
        servers.append(v4_srv)
        actual_port = v4_srv.server_address[1]
        try:
            v6_srv = ThreadedIPv6HTTPServer(("::1", actual_port), BoundHandler)
            servers.append(v6_srv)
        except OSError:
            pass
    else:
        primary_srv = ReusableThreadingHTTPServer((host, port), BoundHandler)
        servers.append(primary_srv)
        actual_port = primary_srv.server_address[1]

    allowed_hosts = {
        f"127.0.0.1:{actual_port}",
        f"localhost:{actual_port}",
        f"[::1]:{actual_port}",
    }

    extra_clean = (extra_host or "").strip()
    if extra_clean and extra_clean not in ("0.0.0.0", "::", "*", "127.0.0.1", "localhost"):
        try:
            extra_ip = socket.gethostbyname(extra_clean)
            if extra_ip and extra_ip not in ("0.0.0.0", "127.0.0.1", host):
                extra_srv = ReusableThreadingHTTPServer((extra_ip, actual_port), BoundHandler)
                servers.append(extra_srv)
                logger.info(
                    "Additional interface listener active on http://%s:%d (%s:%d)",
                    extra_clean,
                    actual_port,
                    extra_ip,
                    actual_port,
                )
            allowed_hosts.update({extra_clean.lower(), f"{extra_clean.lower()}:{actual_port}"})
        except OSError as exc:
            logger.warning("Could not bind extra host %s: %s", extra_clean, exc)

    context.allowed_origin_hosts = allowed_hosts
    return servers


def main() -> None:
    parser = argparse.ArgumentParser(description="LiveEcho (现场回响) v2 — China Concert Tracker")
    parser.add_argument(
        "--host",
        default=os.getenv("CONCERT_TRACKER_HOST", "127.0.0.1"),
        help="Primary bind address (defaults to 127.0.0.1; set 0.0.0.0 inside containers)",
    )
    parser.add_argument(
        "--extra-host",
        default=os.getenv("CONCERT_TRACKER_EXTRA_HOST", ""),
        help="Optional additional hostname interface to bind alongside loopback",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT") or os.getenv("CONCERT_TRACKER_PORT") or "8788"),
        help="TCP port (honors $PORT for Render/Railway/Fly/Cloud Run; default: 8788)",
    )
    args = parser.parse_args()

    allow_public = (
        os.getenv("CONCERT_TRACKER_ALLOW_PUBLIC_BIND") == "1"
        or os.getenv("CONTAINER_RUNTIME") == "1"
    )
    if args.host in ("0.0.0.0", "::", "*") and not allow_public:
        raise SystemExit(
            "Refusing wildcard bind without CONTAINER_RUNTIME=1 or CONCERT_TRACKER_ALLOW_PUBLIC_BIND=1."
        )

    ctx = AppContext(enable_scheduler=True)
    servers = create_http_servers(args.host, args.port, ctx, extra_host=args.extra_host)
    bound_port = servers[0].server_address[1]

    for extra_srv in servers[1:]:
        t = threading.Thread(target=extra_srv.serve_forever, daemon=True)
        t.start()

    logger.info("LiveEcho (现场回响) v2 listening on http://%s:%d", args.host, bound_port)
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down LiveEcho...")
    finally:
        ctx.stop()
        for srv in servers:
            srv.shutdown()


if __name__ == "__main__":
    main()
