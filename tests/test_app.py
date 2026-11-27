"""Automated functional and security verification test suite for LiveEcho v2 (all 6 China concert features)."""

from __future__ import annotations

import base64
import datetime
import gzip
import http.cookies
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app.discovery import parse_hardened_rss_xml, parse_showstart_html
from app.parser import (
    SHANGHAI_TZ,
    analyze_festival_groups,
    compute_12306_plan,
    compute_stub_wall_stats,
    parse_concert_announcement,
)
from app.poster_ocr import generate_sample_tour_poster_png, validate_and_sanitize_poster_upload
from app.reminders import generate_ics_for_concerts
from app.security import SlidingWindowRateLimiter, validate_outbound_https_url
from server import AppContext, create_http_servers


class ParserAndSixFeaturesTests(unittest.TestCase):
    def test_single_stop_with_ticket_rounds_and_refund_tiers(self) -> None:
        now = datetime.datetime(2026, 11, 16, 19, 0, tzinfo=SHANGHAI_TZ)
        raw = (
            "【官宣】草东没有派对 2026 专场演出（杭州站）\n"
            "演出时间：2026年12月19日 19:30\n"
            "演出场馆：杭州奥体中心体育馆\n"
            "票价：¥380 / 580 / 780元\n"
            "优先购开启：2026年11月22日 11:18（纷玩岛）\n"
            "正式开票时间：2026年11月23日 12:18（大麦）\n"
            "退票规则：开票后48小时内无条件退票\n"
            "退票规则：2026年12月05日 12:00前退票收取20%手续费\n"
            "2026年12月15日 12:00停止退票\n"
            "https://www.damai.cn/item.htm?id=12345"
        )
        res = parse_concert_announcement(raw, now=now)
        self.assertFalse(res["multi_stop"])
        item = res["items"][0]
        self.assertEqual(item["artist_name"], "草东没有派对")
        self.assertEqual(item["city"], "杭州")
        self.assertEqual(item["venue"], "杭州奥体中心体育馆")
        self.assertEqual(len(item["ticket_rounds"]), 2)
        self.assertEqual(len(item["refund_tiers"]), 3)
        self.assertEqual(item["refund_tiers"][0]["fee_percent"], 0)
        self.assertTrue(item["refund_tiers"][0]["expect_return_drop"])
        self.assertEqual(item["refund_tiers"][1]["fee_percent"], 20)
        self.assertEqual(item["refund_tiers"][2]["fee_percent"], 100)
        self.assertFalse(item["refund_tiers"][2]["expect_return_drop"])

    def test_culture_bureau_approval_early_warning_parsing(self) -> None:
        now = datetime.datetime(2026, 11, 16, 19, 0, tzinfo=SHANGHAI_TZ)
        raw = (
            "广东省文化和旅游厅关于准予举办陈奕迅2027巡回演唱会（深圳站）的行政许可决定\n"
            "许可文号：粤文旅审〔2026〕1928号\n"
            "举办日期：2027年01月16日 19:30\n"
            "演出场所：深圳大运中心体育场\n"
            "申请演出演员：陈奕迅\n"
        )
        res = parse_concert_announcement(raw, now=now)
        item = res["items"][0]
        self.assertEqual(item["status"], "approved_pending")
        self.assertEqual(item["approval_doc_no"], "粤文旅审〔2026〕1928号")
        self.assertEqual(item["approval_source"], "广东省文化和旅游厅")
        self.assertEqual(item["city"], "深圳")
        self.assertEqual(item["artist_name"], "陈奕迅")

    def test_festival_mode_single_day_overlap_and_clash_detection(self) -> None:
        now = datetime.datetime(2026, 11, 16, 19, 0, tzinfo=SHANGHAI_TZ)
        raw = (
            "2026广州超级草莓音乐节 全阵容时刻表\n"
            "演出时间：2026年12月05日 13:30\n"
            "地点：[广州]南沙音乐秀场\n"
            "2026年12月05日\n"
            "草莓舞台 19:30-20:15 新裤子\n"
            "爱舞台 19:50-20:35 落日飞车\n"
            "2026年12月06日\n"
            "草莓舞台 20:10-20:55 万能青年旅店\n"
        )
        parsed = parse_concert_announcement(raw, now=now)
        fest = parsed["items"][0]
        fest["id"] = 101
        self.assertEqual(fest["event_kind"], "festival")
        self.assertEqual(len(fest["lineup"]), 3)

        followed = [{"name": "新裤子", "aliases": []}, {"name": "落日飞车", "aliases": []}]
        groups = analyze_festival_groups([fest], followed)
        self.assertEqual(len(groups), 1)
        self.assertIn("2026-12-05", groups[0]["best_single_day"])
        self.assertEqual(len(groups[0]["clashes"]), 1)
        self.assertIn("重叠 25 分钟", groups[0]["clashes"][0])

    def test_12306_cross_city_rail_calculation_and_ics_export(self) -> None:
        concert = {
            "id": 55,
            "artist_name": "万能青年旅店",
            "title": "杭州专场",
            "city": "杭州",
            "venue": "杭州奥体中心体育馆",
            "show_time": "2026-12-19 19:30",
            "platform": "大麦",
            "price_text": "¥680",
            "status": "upcoming_drop",
            "rail_booked": False,
            "ticket_rounds": [{"id": 1, "round_label": "一开", "sale_time": "2026-11-23 12:18", "platform": "大麦"}],
            "refund_tiers": [{"id": 2, "tier_label": "无条件退截止", "cutoff_time": "2026-11-25 12:18", "fee_percent": 0, "expect_return_drop": True}],
        }
        same_city = compute_12306_plan("杭州", concert)
        self.assertFalse(same_city["is_cross_city"])

        cross_plan = compute_12306_plan("上海", concert)
        self.assertTrue(cross_plan["is_cross_city"])
        self.assertEqual(cross_plan["outbound_travel_date"], "2026-12-19")
        # 15 days inclusive before Dec 19 = Dec 05
        self.assertEqual(cross_plan["outbound_12306_sale_time"], "2026-12-05 08:00")

        ics = generate_ics_for_concerts([concert], home_city="上海")
        self.assertIn("UID:liveecho-drop-55-1@concert-tracker.local", ics)
        self.assertIn("UID:liveecho-refund-55-2@concert-tracker.local", ics)
        self.assertIn("UID:liveecho-12306-55@concert-tracker.local", ics)
        self.assertIn("UID:liveecho-show-55@concert-tracker.local", ics)

    def test_stub_wall_stats_and_poster_cdr_validation(self) -> None:
        stats = compute_stub_wall_stats(
            [
                {"status": "attended", "city": "深圳", "artist_name": "草东没有派对", "actual_paid_yuan": 280, "venue_rating": 5},
                {"status": "attended", "city": "上海", "artist_name": "万能青年旅店", "actual_paid_yuan": 680, "venue_rating": 4},
                {"status": "upcoming_drop", "city": "北京", "artist_name": "新裤子", "actual_paid_yuan": 580, "venue_rating": 0},
            ]
        )
        self.assertEqual(stats["attended_count"], 2)
        self.assertEqual(stats["unlocked_city_count"], 2)
        self.assertEqual(stats["total_spent_yuan"], 960)
        self.assertEqual(stats["avg_venue_rating"], 4.5)

        with tempfile.TemporaryDirectory() as tmpd:
            uploads = Path(tmpd) / "uploads"
            # Reject disguised text file claiming to be .png (magic bytes check)
            with self.assertRaises(ValueError):
                validate_and_sanitize_poster_upload("evil.png", b"not-a-real-png-script", uploads)
            # Reject disallowed extension (.svg)
            with self.assertRaises(ValueError):
                validate_and_sanitize_poster_upload("vector.svg", b"<svg></svg>", uploads)

            # Valid generated sample tour poster passes CDR and preserves schedule hint
            sample_png = generate_sample_tour_poster_png()
            saved = validate_and_sanitize_poster_upload("tour.png", sample_png, uploads)
            self.assertIn("万能青年旅店", saved["embedded_schedule_hint"])
            # Confirm CDR stripped custom PNG text chunks from the stored file on disk!
            stored_bytes = (uploads / saved["stored_filename"]).read_bytes()
            self.assertNotIn(b"liveecho_schedule", stored_bytes)

    def test_showstart_and_rss_xxe_guards(self) -> None:
        now = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=SHANGHAI_TZ)
        sample_html = """
        <a href="/event/999002" class="show-item item">
          <div class="title">2026重庆草莓音乐节</div>
          <div class="artist">艺人：万能青年旅店</div>
          <div class="price">价格：<span>¥298起</span></div>
          <div class="time">时间：2026/11/28 13:00</div>
          <div class="addr"><i class="el-icon-location"></i>[重庆]国际博览中心</div>
        </a>
        """
        items = parse_showstart_html(sample_html, "万能青年旅店", now=now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["event_kind"], "festival")

        malicious_xml = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rss></rss>'
        with self.assertRaises(ValueError):
            parse_hardened_rss_xml(malicious_xml, "万能青年旅店")

        # Ensure solo tours containing "嘉年华" + "演唱会" are NOT misclassified as festivals
        solo_carnival_html = """
        <a href="/event/999003" class="show-item item">
          <div class="title">周杰伦 2027 嘉年华世界巡回演唱会</div>
          <div class="artist">艺人：周杰伦</div>
          <div class="price">价格：<span>¥780起</span></div>
          <div class="time">时间：2027/01/15 19:30</div>
          <div class="addr"><i class="el-icon-location"></i>[香港]启德主场馆</div>
        </a>
        """
        solo_items = parse_showstart_html(solo_carnival_html, "周杰伦", now=now)
        self.assertEqual(len(solo_items), 1)
        self.assertEqual(solo_items[0]["event_kind"], "concert")

    def test_traditional_chinese_hk_macau_tw_and_multi_night_parsing(self) -> None:
        now = datetime.datetime(2026, 11, 16, 19, 0, tzinfo=SHANGHAI_TZ)
        hk_raw = (
            "【重磅】陳奕迅 FEAR AND DREAMS 世界巡迴演唱會（香港站）\n"
            "演出時間：2026年12月19日-21日 20:15\n"
            "演出場館：紅磡香港體育館\n"
            "票價：HK$1280 / 980 / 680\n"
            "信用卡優先購：2026年11月20日 10:00（Cityline）\n"
            "公開發售：2026年11月22日 10:00（城市售票網）\n"
            "開票後48小時內無條件退票\n"
            "https://www.urbtix.hk/"
        )
        res = parse_concert_announcement(hk_raw, now=now)
        self.assertTrue(res["multi_stop"])
        self.assertEqual(len(res["items"]), 3)
        first = res["items"][0]
        self.assertEqual(first["artist_name"], "陈奕迅")
        self.assertEqual(first["city"], "香港")
        self.assertEqual(first["region"], "gba")
        self.assertEqual(first["venue"], "紅磡香港體育館")
        self.assertEqual(first["price_text"], "HK$1280/980/680")
        self.assertEqual(len(first["ticket_rounds"]), 2)
        self.assertEqual(first["ticket_rounds"][0]["platform"], "Cityline")
        self.assertEqual(first["ticket_rounds"][1]["platform"], "城市售票网")
        self.assertEqual(len(first["refund_tiers"]), 1)

        # HK & Macau get cross-border 12306 plans; Taipei does not
        hk_rail = compute_12306_plan("广州", first)
        self.assertTrue(hk_rail["is_cross_city"])
        self.assertIn("西九龙", hk_rail["corridor"])

        tw_rail = compute_12306_plan("上海", {**first, "city": "臺北"})
        self.assertFalse(tw_rail["is_cross_city"])

    def test_midnight_festival_clash_and_rfc5545_75_octet_folding(self) -> None:
        fest = {
            "id": 202,
            "artist_name": "重塑雕像的权利 / 新裤子",
            "title": "2026 跨年电子摇滚音乐节",
            "festival_name": "2026 跨年电子摇滚音乐节",
            "event_kind": "festival",
            "city": "深圳",
            "show_time": "2026-12-31 16:00",
            "lineup": [
                {"artist": "重塑雕像的权利", "stage": "A舞台", "day_date": "2026-12-31", "set_start": "23:30", "set_end": "00:15"},
                {"artist": "新裤子", "stage": "B舞台", "day_date": "2026-12-31", "set_start": "23:50", "set_end": "00:35"},
            ],
            "ticket_rounds": [],
            "refund_tiers": [],
            "notes": "跨年场超长中文描述测试" * 15,
        }
        groups = analyze_festival_groups([fest], [{"name": "重塑雕像的权利"}, {"name": "新裤子"}])
        self.assertEqual(len(groups[0]["clashes"]), 1)
        self.assertIn("重叠 25 分钟", groups[0]["clashes"][0])

        ics = generate_ics_for_concerts([fest], home_city="上海")
        for physical_line in ics.split("\r\n"):
            # Must decode as valid UTF-8 (never split inside a 3-byte CJK character) and never exceed 75 octets
            encoded = physical_line.encode("utf-8")
            self.assertLessEqual(len(encoded), 75, f"Line exceeded 75 octets: {physical_line!r}")

        unfolded = ics.replace("\r\n ", "")
        self.assertIn("UID:liveecho-show-202@concert-tracker.local", unfolded)
        self.assertIn("【演出】重塑雕像的权利 / 新裤子", unfolded)

    def test_rate_limiter_eviction(self) -> None:
        rl = SlidingWindowRateLimiter()
        ok, _ = rl.allow("temp_bucket", 5, 0.02)
        self.assertTrue(ok)
        self.assertEqual(rl.tracked_key_count, 1)
        time.sleep(0.03)
        pruned = rl.prune(max_idle_seconds=0.01)
        self.assertEqual(pruned, 1)
        self.assertEqual(rl.tracked_key_count, 0)


class EndToEndSecurityAndApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ctx = AppContext(data_dir=Path(self.tmp_dir.name), enable_scheduler=False)
        self.servers = create_http_servers("127.0.0.1", 0, self.ctx)
        self.port = self.servers[0].server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.threads = [threading.Thread(target=srv.serve_forever, daemon=True) for srv in self.servers]
        for t in self.threads:
            t.start()

    def tearDown(self) -> None:
        self.ctx.stop()
        for s in self.servers:
            s.shutdown()
            s.server_close()
        self.tmp_dir.cleanup()

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes, dict[str, str]]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        if cookies:
            req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
        for hk, hv in (headers or {}).items():
            req.add_header(hk, hv)

        new_cookies: dict[str, str] = {}
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                for sc in resp.headers.get_all("Set-Cookie") or []:
                    jar = http.cookies.SimpleCookie()
                    jar.load(sc)
                    for ck, morsel in jar.items():
                        new_cookies[ck] = morsel.value
                body = resp.read()
        except urllib.error.HTTPError as err:
            status = err.code
            resp_headers = {k.lower(): v for k, v in err.headers.items()}
            body = err.read()
        return status, resp_headers, body, new_cookies

    def test_security_headers_method_allowlist_and_ssrf(self) -> None:
        status, hdrs, _, _ = self._request("GET", "/")
        self.assertEqual(status, 200)
        csp = hdrs.get("content-security-policy", "")
        self.assertIn("nonce-", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(hdrs.get("x-frame-options"), "SAMEORIGIN")
        self.assertEqual(hdrs.get("x-content-type-options"), "nosniff")

        for verb in ("DELETE", "PUT", "TRACE"):
            st_v, _, _, _ = self._request(verb, "/api/concerts/delete")
            self.assertEqual(st_v, 405)

        st_trav, _, _, _ = self._request("GET", "/static/..%2fserver.py")
        self.assertEqual(st_trav, 404)

        with self.assertRaises(ValueError):
            validate_outbound_https_url("http://example.com/feed.xml")
        with self.assertRaises(ValueError):
            validate_outbound_https_url("https://127.0.0.1:8788/api")

    def test_poster_upload_cdr_attachment_headers_and_tenant_isolation(self) -> None:
        _, _, raw_pre, c1 = self._request("GET", "/api/auth/status")
        pre_csrf = json.loads(raw_pre)["csrf_token"]
        st_reg, _, raw_reg, c_alice = self._request(
            "POST",
            "/api/auth/register",
            {
                "username": "alice",
                "password": "strong-password-123",
                "home_city": "上海",
                "include_demo_concerts": True,
            },
            cookies=c1,
            headers={"X-CSRF-Token": pre_csrf},
        )
        self.assertEqual(st_reg, 201)
        alice_csrf = json.loads(raw_reg)["csrf_token"]
        alice_cookies = {**c1, **c_alice}

        # Test built-in sample poster upload -> CDR -> OCR parse
        st_up, _, raw_up, _ = self._request(
            "POST",
            "/api/posters/upload",
            {"use_sample_poster": True},
            cookies=alice_cookies,
            headers={"X-CSRF-Token": alice_csrf},
        )
        self.assertEqual(st_up, 200)
        up_data = json.loads(raw_up)
        poster_uuid = up_data["poster_uuid"]
        self.assertEqual(len(up_data["parsed"]["items"]), 3)

        # Download poster as Alice -> must enforce Content-Disposition: attachment + nosniff
        st_dl, dl_hdrs, dl_bytes, _ = self._request(
            "GET",
            f"/api/posters/download?uuid={poster_uuid}",
            cookies=alice_cookies,
        )
        self.assertEqual(st_dl, 200)
        self.assertIn("attachment", dl_hdrs.get("content-disposition", ""))
        self.assertEqual(dl_hdrs.get("x-content-type-options"), "nosniff")
        self.assertTrue(dl_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

        # Reject fake executable bytes uploaded as .png
        fake_b64 = base64.b64encode(b"MZ-fake-executable").decode("ascii")
        st_fake, _, _, _ = self._request(
            "POST",
            "/api/posters/upload",
            {"filename": "bad.png", "image_base64": fake_b64},
            cookies=alice_cookies,
            headers={"X-CSRF-Token": alice_csrf},
        )
        self.assertEqual(st_fake, 400)

        # Register Bob -> Bob cannot download Alice's poster
        _, _, raw_b_pre, c2 = self._request("GET", "/api/auth/status")
        b_pre_csrf = json.loads(raw_b_pre)["csrf_token"]
        _, _, _, c_bob = self._request(
            "POST",
            "/api/auth/register",
            {"username": "bob", "password": "another-strong-password", "include_demo_concerts": False},
            cookies=c2,
            headers={"X-CSRF-Token": b_pre_csrf},
        )
        bob_cookies = {**c2, **c_bob}
        st_cross_dl, _, _, _ = self._request(
            "GET",
            f"/api/posters/download?uuid={poster_uuid}",
            cookies=bob_cookies,
        )
        self.assertEqual(st_cross_dl, 404)

    def test_gzip_etag_edit_notes_dedupe_orphan_cleanup_and_backup(self) -> None:
        # 1. Gzip + ETag 304 Not Modified on static JS asset
        st_js, js_hdrs, js_raw, _ = self._request(
            "GET",
            "/static/app.js",
            headers={"Accept-Encoding": "gzip"},
        )
        self.assertEqual(st_js, 200)
        self.assertEqual(js_hdrs.get("content-encoding"), "gzip")
        decompressed = gzip.decompress(js_raw).decode("utf-8")
        self.assertIn("LiveEcho", decompressed)
        etag = js_hdrs.get("etag", "")
        self.assertTrue(etag.startswith('W/"'))

        st_304, _, body_304, _ = self._request(
            "GET",
            "/static/app.js",
            headers={"If-None-Match": etag},
        )
        self.assertEqual(st_304, 304)
        self.assertEqual(body_304, b"")

        # 2. Register user, upload poster, create concert with notes, verify natural-key dedupe + edit preservation
        _, _, raw_pre, c1 = self._request("GET", "/api/auth/status")
        pre_csrf = json.loads(raw_pre)["csrf_token"]
        _, _, raw_reg, c_u1 = self._request(
            "POST",
            "/api/auth/register",
            {"username": "fan_one", "password": "very-strong-password", "include_demo_concerts": False},
            cookies=c1,
            headers={"X-CSRF-Token": pre_csrf},
        )
        csrf1 = json.loads(raw_reg)["csrf_token"]
        u1_cookies = {**c1, **c_u1}

        _, _, raw_up, _ = self._request(
            "POST",
            "/api/posters/upload",
            {"use_sample_poster": True},
            cookies=u1_cookies,
            headers={"X-CSRF-Token": csrf1},
        )
        poster_uuid = json.loads(raw_up)["poster_uuid"]
        poster_disk_path = self.ctx.uploads_dir / f"{poster_uuid}.png"
        self.assertTrue(poster_disk_path.is_file())

        concert_payload = {
            "artist_name": "万能青年旅店",
            "title": "石家庄跨年专场",
            "city": "石家庄",
            "venue": "河北省艺术中心",
            "show_time": "2026-12-31 19:30",
            "status": "approved_pending",
            "approval_doc_no": "冀文旅许〔2026〕099号",
            "approval_source": "河北省文化和旅游厅",
            "poster_uuid": poster_uuid,
            "notes": "抢一楼前十排中轴位！",
        }
        st_c1, _, raw_c1, _ = self._request(
            "POST",
            "/api/concerts/create",
            concert_payload,
            cookies=u1_cookies,
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(st_c1, 201)
        cid = json.loads(raw_c1)["ids"][0]

        # Duplicate create with identical natural key returns the existing ID instead of duplicating
        _, _, raw_c2, _ = self._request(
            "POST",
            "/api/concerts/create",
            concert_payload,
            cookies=u1_cookies,
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(json.loads(raw_c2)["ids"][0], cid)

        # Update concert and ensure notes + approval_source are preserved
        st_upd, _, _, _ = self._request(
            "POST",
            "/api/concerts/update",
            {**concert_payload, "id": cid, "price_text": "¥680"},
            cookies=u1_cookies,
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(st_upd, 200)

        # 3. Export JSON backup -> verify attachment header & no leaked password_hash
        st_exp, exp_hdrs, exp_bytes, _ = self._request(
            "GET",
            "/api/backup/export",
            cookies=u1_cookies,
        )
        self.assertEqual(st_exp, 200)
        self.assertIn("attachment", exp_hdrs.get("content-disposition", ""))
        vault = json.loads(exp_bytes.decode("utf-8"))
        self.assertNotIn("password_hash", exp_bytes.decode("utf-8"))
        self.assertEqual(len(vault["concerts"]), 1)
        self.assertEqual(vault["concerts"][0]["notes"], "抢一楼前十排中轴位！")
        self.assertEqual(vault["concerts"][0]["approval_source"], "河北省文化和旅游厅")

        # 4. Delete concert -> verify orphaned poster file on disk is cleaned up automatically
        st_del, _, _, _ = self._request(
            "POST",
            "/api/concerts/delete",
            {"id": cid},
            cookies=u1_cookies,
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(st_del, 200)
        self.assertFalse(poster_disk_path.exists())

        # 5. Restore vault from JSON backup -> concert + notes come right back
        st_imp, _, raw_imp, _ = self._request(
            "POST",
            "/api/backup/import",
            vault,
            cookies=u1_cookies,
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(st_imp, 200)
        self.assertEqual(json.loads(raw_imp)["concerts_imported"], 1)

    def test_public_website_version_showcase_parse_preview_and_ics(self) -> None:
        from unittest import mock

        mocked_live_feed = {
            "items": [
                {
                    "id": 309491,
                    "artist_name": "Demxntia",
                    "artist_category": "intl_west",
                    "title": "美国电子流行唱作人【Demxntia】2026巡演 广州站",
                    "city": "广州",
                    "region": "gba",
                    "venue": "广州疆进酒·OMNI SPACE",
                    "show_time": "2026-12-19 20:00",
                    "price_text": "¥220起",
                    "platform": "秀动",
                    "ticket_url": "https://www.showstart.com/event/309491",
                    "status": "upcoming_drop",
                    "event_kind": "concert",
                    "data_source": "秀动 ShowStart 实时在售",
                    "is_live_verified": True,
                    "ticket_rounds": [],
                    "refund_tiers": [],
                },
                {
                    "id": 312367,
                    "artist_name": "Schoolgirl Byebye",
                    "artist_category": "cn",
                    "title": "Schoolgirl Byebye 2026巡演 上海站",
                    "city": "上海",
                    "region": "jzh",
                    "venue": "梅赛德斯-奔驰文化中心",
                    "show_time": "2026-12-20 19:30",
                    "price_text": "¥180起",
                    "platform": "秀动",
                    "ticket_url": "https://www.showstart.com/event/312367",
                    "status": "upcoming_drop",
                    "event_kind": "concert",
                    "data_source": "秀动 ShowStart 实时在售",
                    "is_live_verified": True,
                    "ticket_rounds": [],
                    "refund_tiers": [],
                },
            ],
            "fetched_at": "2026-11-27 10:00",
            "sources": ["秀动 ShowStart 实时在售", "Songkick 全球排期实时核验"],
        }

        with mock.patch("server.discover_live_china_music_feed", return_value=mocked_live_feed):
            st_site, site_hdrs, site_html, site_cookies = self._request("GET", "/website")
            self.assertEqual(st_site, 200)
            self.assertIn("nonce-", site_hdrs.get("content-security-policy", ""))
            self.assertIn("现场回响 LiveEcho", site_html.decode("utf-8"))

            st_sc, sc_hdrs, raw_sc, sc_cookies = self._request("GET", "/api/public/showcase?home_city=%E5%B9%BF%E5%B7%9E", cookies=site_cookies)
            self.assertEqual(st_sc, 200)
            sc_etag = sc_hdrs.get("etag", "")
            self.assertTrue(sc_etag.startswith('W/"'))
            self.assertIn("private", sc_hdrs.get("cache-control", ""))
            sc_data = json.loads(raw_sc)
            self.assertEqual(len(sc_data["concerts"]), 2)
            self.assertTrue(sc_data["festival_demo"]["is_demo_simulator"])
            merged_cookies = {**site_cookies, **sc_cookies}
            csrf_tok = sc_data["csrf_token"]

            # Conditional ETag check must return 304 Not Modified with empty body
            st_304, hdrs_304, raw_304, _ = self._request(
                "GET",
                "/api/public/showcase?home_city=%E5%B9%BF%E5%B7%9E",
                cookies=merged_cookies,
                headers={"If-None-Match": sc_etag},
            )
            self.assertEqual(st_304, 304)
            self.assertEqual(raw_304, b"")
            self.assertEqual(hdrs_304.get("etag"), sc_etag)

            # Explicit ?refresh=1 bypasses ETag 304
            st_rf, _, raw_rf, _ = self._request(
                "GET",
                "/api/public/showcase?home_city=%E5%B9%BF%E5%B7%9E&refresh=1",
                cookies=merged_cookies,
                headers={"If-None-Match": sc_etag},
            )
            self.assertEqual(st_rf, 200)
            self.assertEqual(len(json.loads(raw_rf)["concerts"]), 2)

            # CSRF required on /api/public/parse-preview
            st_no_csrf, _, _, _ = self._request("POST", "/api/public/parse-preview", {"text": "2026年12月19日 上海 万能青年旅店"})
            self.assertEqual(st_no_csrf, 403)

            st_parse, _, raw_parse, _ = self._request(
                "POST",
                "/api/public/parse-preview",
                {"text": "【官宣】万能青年旅店 2026年12月19日 19:30 南京 江苏大剧院\n正式开票：2026年11月25日 12:18（大麦）", "home_city": "上海"},
                cookies=merged_cookies,
                headers={"X-CSRF-Token": csrf_tok},
            )
            self.assertEqual(st_parse, 200)
            parsed_payload = json.loads(raw_parse)
            self.assertEqual(parsed_payload["items"][0]["city"], "南京")
            self.assertTrue(parsed_payload["items"][0]["rail_plan"]["is_cross_city"])

            st_ics, ics_hdrs, ics_bytes, _ = self._request("GET", "/api/public/showcase-ics?id=309491&home_city=%E5%8C%97%E4%BA%AC")
            self.assertEqual(st_ics, 200)

            # Security & functional tests for POST /api/public/parse-festival-photo
            import io
            from PIL import Image
            from PIL.PngImagePlugin import PngInfo

            # 1) Missing CSRF token must be rejected with 403
            st_no_csrf_img, _, _, _ = self._request(
                "POST",
                "/api/public/parse-festival-photo",
                {"filename": "schedule.png", "image_base64": "aGVsbG8="},
            )
            self.assertEqual(st_no_csrf_img, 403)

            # 2) Spoofed extension (.svg) / non-image bytes must be rejected with 400
            st_bad_ext, _, _, _ = self._request(
                "POST",
                "/api/public/parse-festival-photo",
                {
                    "filename": "evil.svg",
                    "image_base64": base64.b64encode(b"<svg onload=alert(1)></svg>").decode("ascii"),
                },
                cookies=merged_cookies,
                headers={"X-CSRF-Token": csrf_tok},
            )
            self.assertEqual(st_bad_ext, 400)

            st_bad_magic, _, _, _ = self._request(
                "POST",
                "/api/public/parse-festival-photo",
                {
                    "filename": "fake.png",
                    "image_base64": base64.b64encode(b"NOT_A_REAL_PNG_PAYLOAD").decode("ascii"),
                },
                cookies=merged_cookies,
                headers={"X-CSRF-Token": csrf_tok},
            )
            self.assertEqual(st_bad_magic, 400)

            # 3) Valid PNG -> CDR sanitization + mocked Vision OCR returns structured clash timetable
            img = Image.new("RGB", (320, 180), color=(248, 244, 236))
            meta = PngInfo()
            meta.add_text("liveecho_schedule", "2026-11-28 | 草莓舞台 | 万能青年旅店 | 20:10-21:00\n2026-11-28 | 爱舞台 | 回春丹乐队 | 20:25-21:10", zip=False)
            buf = io.BytesIO()
            img.save(buf, format="PNG", pnginfo=meta)
            b64_png = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

            st_img_ok, _, raw_img_ok, _ = self._request(
                "POST",
                "/api/public/parse-festival-photo",
                {
                    "filename": "../traversal/chongqing_timetable.png",
                    "image_base64": b64_png,
                    "festival_name": "2026重庆草莓音乐节",
                    "default_date": "2026-11-28",
                    "known_bands": ["万能青年旅店", "回春丹乐队"],
                },
                cookies=merged_cookies,
                headers={"X-CSRF-Token": csrf_tok},
            )
            self.assertEqual(st_img_ok, 200)
            img_data = json.loads(raw_img_ok)
            self.assertTrue(img_data["ok"])
            self.assertEqual(len(img_data["slots"]), 2)
            self.assertEqual(img_data["slots"][0]["artist"], "万能青年旅店")
            self.assertEqual(img_data["slots"][0]["set_start"], "20:10")
            self.assertEqual(img_data["slots"][1]["artist"], "回春丹乐队")
            self.assertTrue(img_data["preview_data_url"].startswith("data:image/png;base64,"))
            # Verify CDR stripped custom text chunks from returned sanitized PNG
            sanitized_bytes = base64.b64decode(img_data["preview_data_url"].split(",", 1)[1])
            with Image.open(io.BytesIO(sanitized_bytes)) as clean_check:
                self.assertNotIn("liveecho_schedule", clean_check.info)
            self.assertIn("attachment", ics_hdrs.get("content-disposition", ""))
            self.assertIn("BEGIN:VCALENDAR", ics_bytes.decode("utf-8"))

            st_fav_ics, _, fav_ics_bytes, _ = self._request(
                "GET",
                "/api/public/showcase-ics?artists=Demxntia&home_city=%E4%B8%8A%E6%B5%B7",
            )
            self.assertEqual(st_fav_ics, 200)
            fav_ics_txt = fav_ics_bytes.decode("utf-8")
            self.assertIn("Demxntia", fav_ics_txt)
            self.assertNotIn("Schoolgirl Byebye", fav_ics_txt)

            # Verify Dua Lipa truthfully returns 0 China shows (zero fabricated dates!) + real Songkick global events
            with mock.patch("app.discovery.search_apple_music_artists", return_value=[]), mock.patch(
                "app.discovery.search_musicbrainz_artist_aliases", return_value={}
            ), mock.patch("app.discovery.discover_showstart_for_artist", return_value=[]), mock.patch(
                "app.discovery.discover_songkick_for_artist",
                return_value={
                    "china_events": [],
                    "global_events": [
                        {
                            "artist_name": "Dua Lipa",
                            "title": "Coachella 2027",
                            "city": "Indio",
                            "country": "US",
                            "venue": "Empire Polo Club",
                            "show_time": "2027-04-09 19:30",
                            "platform": "Songkick",
                            "ticket_url": "https://www.songkick.com/festivals/3794121",
                            "data_source": "Songkick 全球排期实时",
                        }
                    ],
                },
            ):
                st_dl, _, raw_dl, _ = self._request("GET", "/api/public/artist-preview?q=Dua%20Lipa")
                self.assertEqual(st_dl, 200)
                dl_data = json.loads(raw_dl)
                self.assertEqual(dl_data["primary_profile"]["name"], "Dua Lipa")
                self.assertEqual(dl_data["upcoming_cities"], [])
                self.assertEqual(len(dl_data["global_concerts"]), 1)
                self.assertEqual(dl_data["global_concerts"][0]["city"], "Indio")

            st_shewai, _, raw_shewai, _ = self._request(
                "POST",
                "/api/public/parse-preview",
                {
                    "text": "上海市文化和旅游局准予举办 Ed Sheeran 上海演唱会\n许可文号：沪文旅许〔2026〕涉外0412号\n举办日期：2026年12月28日 19:30\n东方体育中心",
                    "home_city": "北京",
                },
                cookies=merged_cookies,
                headers={"X-CSRF-Token": csrf_tok},
            )
            self.assertEqual(st_shewai, 200)
            shewai_item = json.loads(raw_shewai)["items"][0]
            self.assertEqual(shewai_item["approval_doc_no"], "沪文旅许〔2026〕涉外0412号")
            self.assertEqual(shewai_item["artist_name"], "Ed Sheeran")
            self.assertTrue(shewai_item["trip_estimate"]["is_cross_city"])
            self.assertGreater(shewai_item["trip_estimate"]["total_weekend_yuan"], 500)

            # Verify showcase payload includes city_map_nodes, venue_guides, and per-concert trip_estimate
            self.assertGreaterEqual(len(sc_data["city_map_nodes"]), 15)
            self.assertGreaterEqual(len(sc_data["venue_guides"]), 15)
            sh_concert = next((c for c in sc_data["concerts"] if "梅赛德斯" in (c.get("venue") or "")), None)
            self.assertIsNotNone(sh_concert)
            self.assertIsNotNone(sh_concert["venue_guide"])
            self.assertTrue(sh_concert["trip_estimate"]["is_cross_city"])  # home_city=广州 -> 上海

            # Verify CSRF-protected POST /api/public/parse-ics
            st_pics_403, _, _, _ = self._request("POST", "/api/public/parse-ics", {"text": "2026年12月19日 上海 万能青年旅店"})
            self.assertEqual(st_pics_403, 403)
            st_pics, pics_hdrs, pics_bytes, _ = self._request(
                "POST",
                "/api/public/parse-ics",
                {
                    "text": "【官宣】草东没有派对 2026年12月19日 19:30 杭州奥体中心体育馆\n正式开票：2026年11月29日 12:18（大麦）",
                    "home_city": "上海",
                },
                cookies=merged_cookies,
                headers={"X-CSRF-Token": csrf_tok},
            )
            self.assertEqual(st_pics, 200)
            self.assertIn("text/calendar", pics_hdrs.get("content-type", ""))
            self.assertIn("BEGIN:VCALENDAR", pics_bytes.decode("utf-8"))
            self.assertIn("草东没有派对", pics_bytes.decode("utf-8"))

    def test_ephemeral_container_poster_blob_fallback_and_cron_tick_auth(self) -> None:
        _, _, raw_pre, c1 = self._request("GET", "/api/auth/status")
        pre_csrf = json.loads(raw_pre)["csrf_token"]
        _, _, raw_reg, c_u1 = self._request(
            "POST",
            "/api/auth/register",
            {"username": "cloud_user", "password": "very-strong-password", "include_demo_concerts": False},
            cookies=c1,
            headers={"X-CSRF-Token": pre_csrf},
        )
        csrf1 = json.loads(raw_reg)["csrf_token"]
        u1_cookies = {**c1, **c_u1}

        _, _, raw_up, _ = self._request(
            "POST",
            "/api/posters/upload",
            {"use_sample_poster": True},
            cookies=u1_cookies,
            headers={"X-CSRF-Token": csrf1},
        )
        poster_uuid = json.loads(raw_up)["poster_uuid"]
        disk_file = self.ctx.uploads_dir / f"{poster_uuid}.png"
        self.assertTrue(disk_file.is_file())

        # Simulate Render Free container restart wiping local uploads directory
        disk_file.unlink()
        self.assertFalse(disk_file.exists())

        # Download still succeeds seamlessly from uploaded_posters.image_blob in DB
        st_dl, dl_hdrs, dl_bytes, _ = self._request(
            "GET",
            f"/api/posters/download?uuid={poster_uuid}",
            cookies=u1_cookies,
        )
        self.assertEqual(st_dl, 200)
        self.assertTrue(dl_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("attachment", dl_hdrs.get("content-disposition", ""))
        self.assertEqual(dl_hdrs.get("x-content-type-options"), "nosniff")

        # Verify /api/cron/tick fails closed without CRON_SECRET, rejects bad tokens, and succeeds with valid secret
        import os

        old_cron = os.environ.pop("CRON_SECRET", None)
        try:
            st_unconf, _, _, _ = self._request("POST", "/api/cron/tick", {"run_discovery": False})
            self.assertEqual(st_unconf, 503)

            valid_secret = "cron-secret-key-with-at-least-32-chars-xyz"
            os.environ["CRON_SECRET"] = valid_secret

            st_bad, _, _, _ = self._request(
                "POST",
                "/api/cron/tick",
                {"run_discovery": False},
                headers={"Authorization": "Bearer wrong-token"},
            )
            self.assertEqual(st_bad, 401)

            st_ok, _, raw_ok, _ = self._request(
                "POST",
                "/api/cron/tick",
                {"run_discovery": False},
                headers={"Authorization": f"Bearer {valid_secret}"},
            )
            self.assertEqual(st_ok, 200)
            self.assertTrue(json.loads(raw_ok)["ok"])
        finally:
            if old_cron is not None:
                os.environ["CRON_SECRET"] = old_cron
            else:
                os.environ.pop("CRON_SECRET", None)


class TursoCloudAndCronUnitTests(unittest.TestCase):
    """Tests Turso (libSQL) Hrana v2 wire protocol adapter, URL security, and serverless cron catch-up windows."""

    def test_turso_hrana_http_adapter_crud_blob_and_url_security(self) -> None:
        import base64
        import sqlite3
        from app.db import Database
        from app.security import SecretBox
        from app.turso_http import decode_hrana_cell, encode_hrana_arg, normalize_turso_pipeline_url

        # Security rejections on malformed/credentialed URLs
        with self.assertRaises(ValueError):
            normalize_turso_pipeline_url("http://insecure.turso.io", validate_dns=False)
        with self.assertRaises(ValueError):
            normalize_turso_pipeline_url("libsql://user:secret@db.turso.io", validate_dns=False)
        with self.assertRaises(ValueError):
            normalize_turso_pipeline_url("libsql://db.turso.io?authToken=leak", validate_dns=False)

        norm_url = normalize_turso_pipeline_url("libsql://liveecho-demo.turso.io", validate_dns=False)
        self.assertEqual(norm_url, "https://liveecho-demo.turso.io/v2/pipeline")

        # Fail closed when TURSO_DATABASE_URL is set without TURSO_AUTH_TOKEN
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                Database(
                    Path(tmp) / "unused.db",
                    SecretBox(b"x" * 32),
                    turso_url="libsql://liveecho-demo.turso.io",
                    turso_auth_token="",
                )

        # Simulated Turso Hrana /v2/pipeline server backed by in-memory SQLite
        mem_conn = sqlite3.connect(":memory:")

        def fake_turso_transport(url: str, token: str, payload: dict) -> dict:
            self.assertEqual(url, "https://liveecho-demo.turso.io/v2/pipeline")
            self.assertEqual(token, "scoped-turso-jwt-token")
            out_results = []
            for req in payload["requests"]:
                if req["type"] == "close":
                    out_results.append({"type": "ok", "response": {"type": "close"}})
                    continue
                stmt = req["stmt"]
                sql = stmt["sql"]
                args = [decode_hrana_cell(a) for a in stmt.get("args", [])]
                try:
                    cur = mem_conn.execute(sql, tuple(args))
                    cols = [{"name": d[0]} for d in (cur.description or [])]
                    fetched = cur.fetchall() if cur.description else []
                    hrana_rows = [[encode_hrana_arg(v) for v in r] for r in fetched]
                    mem_conn.commit()
                    out_results.append(
                        {
                            "type": "ok",
                            "response": {
                                "type": "execute",
                                "result": {
                                    "cols": cols,
                                    "rows": hrana_rows,
                                    "affected_row_count": max(0, cur.rowcount),
                                    "last_insert_rowid": str(cur.lastrowid) if cur.lastrowid else None,
                                },
                            },
                        }
                    )
                except sqlite3.Error as exc:
                    out_results.append(
                        {"type": "error", "error": {"code": "SQLITE_CONSTRAINT", "message": str(exc)}}
                    )
            return {"baton": None, "base_url": None, "results": out_results}

        try:
            with tempfile.TemporaryDirectory() as tmp:
                db = Database(
                    Path(tmp) / "unused.db",
                    SecretBox(b"m" * 32),
                    turso_url="libsql://liveecho-demo.turso.io",
                    turso_auth_token="scoped-turso-jwt-token",
                    turso_transport_fn=fake_turso_transport,
                )
                self.assertEqual(db.backend_mode, "turso")
                uid = db.create_user("turso_fan", "$2b$12$hash", home_city="深圳")
                tok, csrf = db.create_session(uid)
                sess = db.validate_session(tok)
                self.assertIsNotNone(sess)
                self.assertEqual(sess["home_city"], "深圳")

                sample_png = b"\x89PNG\r\n\x1a\n" + base64.b64decode("AAAA")
                p_uuid = "a" * 32
                db.record_uploaded_poster(uid, p_uuid, f"{p_uuid}.png", "tour.png", 680, 920, image_blob=sample_png)
                self.assertEqual(db.get_uploaded_poster_bytes(uid, p_uuid), sample_png)

                cid = db.create_concert(
                    uid,
                    {
                        "artist_name": "草东没有派对",
                        "title": "深圳专场",
                        "city": "深圳",
                        "show_time": "2026-12-20 20:00",
                        "poster_uuid": p_uuid,
                        "ticket_rounds": [{"round_label": "一开", "sale_time": "2026-11-28 12:00"}],
                    },
                )
                concerts = db.list_concerts(uid)
                self.assertEqual(len(concerts), 1)
                self.assertEqual(concerts[0]["ticket_rounds"][0]["round_label"], "一开")
                self.assertTrue(db.delete_concert(uid, cid))
                self.assertIsNone(db.get_uploaded_poster_bytes(uid, p_uuid))
        finally:
            mem_conn.close()

    def test_cloud_cron_lookback_window_deduplicates_jittered_ticks(self) -> None:
        import datetime
        from unittest import mock
        from app.db import Database
        from app.parser import SHANGHAI_TZ
        from app.reminders import run_reminder_check_cycle
        from app.security import SecretBox
        from scripts.run_cloud_jobs import main as cloud_jobs_main

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db = Database(tmp_path / "concert_tracker.db", SecretBox(b"k" * 32))
            uid = db.create_user("cron_user", "$2b$12$hash")
            db.update_notification_settings(
                uid,
                {"bark_url": "https://api.day.app/demo_key", "lead_minutes": [60]},
            )
            sale_dt = datetime.datetime(2026, 12, 1, 12, 0, tzinfo=SHANGHAI_TZ)
            db.create_concert(
                uid,
                {
                    "artist_name": "陶喆",
                    "title": "成都站",
                    "city": "成都",
                    "show_time": "2026-12-25 19:30",
                    "status": "upcoming_drop",
                    "ticket_rounds": [{"round_label": "一开", "sale_time": sale_dt.strftime("%Y-%m-%d %H:%M")}],
                },
            )

            # Simulate GitHub Actions cron firing 14 minutes late (at T-46m instead of T-60m)
            jittered_now = sale_dt - datetime.timedelta(minutes=46)
            with mock.patch("app.reminders.send_push_or_email_message", return_value={"bark": "ok"}) as m_send:
                sent_1 = run_reminder_check_cycle(db, now=jittered_now, lookback_minutes=22.0)
                self.assertEqual(sent_1, 1)
                self.assertEqual(m_send.call_count, 1)

                # Next 10-minute cron tick at T-39m does NOT re-send the already logged reminder
                sent_2 = run_reminder_check_cycle(
                    db, now=sale_dt - datetime.timedelta(minutes=39), lookback_minutes=22.0
                )
                self.assertEqual(sent_2, 0)

            # Verify standalone CLI runner exits 0 cleanly
            rc = cloud_jobs_main(["--skip-discover", "--data-dir", str(tmp_path)])
            self.assertEqual(rc, 0)

    def test_static_site_builder_generates_strict_csp_bundle(self) -> None:
        from scripts.build_static_site import build_static_site

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "dist"
            stats = build_static_site(out_dir, offline_fixture=True)
            self.assertEqual(stats["concerts"], 1)
            for rel in (
                "index.html",
                "404.html",
                ".nojekyll",
                "favicon.svg",
                "_headers",
                "data/showcase.json",
                "static/website.css",
                "static/website.js",
                "static/static-shim.js",
            ):
                self.assertTrue((out_dir / rel).is_file(), f"Missing static output file: {rel}")

            html = (out_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("Content-Security-Policy", html)
            self.assertNotIn("unsafe-inline", html)
            self.assertNotIn("style=", html)
            self.assertNotIn("__CSP_NONCE__", html)
            self.assertIn('./static/static-shim.js', html)
            self.assertIn('./static/website.js', html)
            self.assertIn('./static/website.css', html)

            shim = (out_dir / "static/static-shim.js").read_text(encoding="utf-8")
            self.assertNotIn("innerHTML", shim)
            self.assertNotIn("outerHTML", shim)
            self.assertNotIn("eval(", shim)

            payload = json.loads((out_dir / "data/showcase.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["static_mode"])
            self.assertEqual(len(payload["concerts"]), 1)


if __name__ == "__main__":
    unittest.main()
