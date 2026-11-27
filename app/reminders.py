"""Calendar (.ics) exporter (drops, refund/return snipers, 12306 rail, showtimes) and push/email dispatcher."""

from __future__ import annotations

import datetime
import email.message
import logging
import re
import smtplib
import socket
import ssl
import urllib.parse
from typing import Any

from app.db import Database
from app.parser import REGION_LABELS, SHANGHAI_TZ, compute_12306_plan
from app.security import _is_disallowed_ip, safe_https_request

logger = logging.getLogger("concert_tracker.reminders")


def _ics_escape(value: str) -> str:
    clean = (value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return clean.replace("\r\n", "\\n").replace("\n", "\\n")


def _fold_ics_line(line: str, max_octets: int = 75) -> str:
    """Folds a single iCalendar content line at <= 75 UTF-8 octets without splitting multi-byte characters (RFC 5545 §3.1)."""
    if len(line.encode("utf-8")) <= max_octets:
        return line

    segments: list[str] = []
    current_chars: list[str] = []
    current_bytes = 0
    limit = max_octets  # First physical line gets 75 octets; continuation lines start with ' ' (1 octet) so get 74

    for ch in line:
        ch_bytes = len(ch.encode("utf-8"))
        if current_chars and (current_bytes + ch_bytes) > limit:
            segments.append("".join(current_chars))
            current_chars = [ch]
            current_bytes = ch_bytes
            limit = max_octets - 1
        else:
            current_chars.append(ch)
            current_bytes += ch_bytes

    if current_chars:
        segments.append("".join(current_chars))

    return "\r\n ".join(segments)


def _parse_local_shanghai_dt(dt_str: str) -> datetime.datetime | None:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            naive = datetime.datetime.strptime(dt_str.strip(), fmt)
            if fmt == "%Y-%m-%d":
                naive = naive.replace(hour=19, minute=30)
            return naive.replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    return None


def generate_ics_for_concerts(
    concerts: list[dict[str, Any]],
    cal_name: str = "现场回响 · 中国演唱会与抢票日历",
    home_city: str = "上海",
) -> str:
    """Generates RFC 5545 iCalendar with ticket drops, refund/return windows, 12306 rail, and showtime events."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LiveEcho//China Concert Tracker v2//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(cal_name)}",
        "X-WR-TIMEZONE:Asia/Shanghai",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Shanghai",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "TZNAME:CST",
        "DTSTART:19700101T000000",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for concert in concerts:
        cid = concert.get("id", "0")
        artist = concert.get("artist_name") or "演出"
        title = concert.get("title") or artist
        city = concert.get("city") or ""
        venue = concert.get("venue") or ""
        platform = concert.get("platform") or "票务平台"
        ticket_url = concert.get("ticket_url") or ""
        price = concert.get("price_text") or "待公布"
        seat_note = concert.get("seat_note") or ""
        status = concert.get("status") or "upcoming_drop"

        # 1. Ticket on-sale (抢票) events
        for tr in concert.get("ticket_rounds") or []:
            sale_dt = _parse_local_shanghai_dt(tr.get("sale_time", ""))
            if not sale_dt:
                continue
            sale_end = sale_dt + datetime.timedelta(minutes=30)
            r_label = tr.get("round_label") or "抢票"
            r_plat = tr.get("platform") or platform
            r_url = tr.get("booking_url") or ticket_url
            rid = tr.get("id", sale_dt.strftime("%Y%m%d%H%M"))

            desc_parts = [
                f"艺人：{artist}",
                f"场次：{title}",
                f"城市/场馆：{city} {venue}".strip(),
                f"抢票轮次：{r_label}（{r_plat}）",
                f"票价：{price}",
                "抢票前检查：1. 预约想看  2. 预填实名观演人身份证  3. 默认收货地址",
            ]
            if r_url:
                desc_parts.append(f"购票链接：{r_url}")

            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:liveecho-drop-{cid}-{rid}@concert-tracker.local",
                    f"DTSTAMP:{now_utc}",
                    f"DTSTART;TZID=Asia/Shanghai:{sale_dt.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID=Asia/Shanghai:{sale_end.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{_ics_escape(f'【抢票·{r_label}】{artist}（{city}站）· {r_plat}')}",
                    f"LOCATION:{_ics_escape(r_plat)}",
                    f"DESCRIPTION:{_ics_escape(chr(10).join(desc_parts))}",
                    "BEGIN:VALARM",
                    "TRIGGER:-PT30M",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(f'30分钟后抢票：{artist} {city}站（请核对实名观演人！）')}",
                    "END:VALARM",
                    "BEGIN:VALARM",
                    "TRIGGER:-PT5M",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(f'5分钟后立即开抢：{artist} {city}站（{r_plat}）')}",
                    "END:VALARM",
                    "END:VEVENT",
                ]
            )

        # 2. Refund Tier Cutoffs & Returned-Ticket Sniping (阶梯退票与回流狙击)
        for rf in concert.get("refund_tiers") or []:
            cut_dt = _parse_local_shanghai_dt(rf.get("cutoff_time", ""))
            if not cut_dt:
                continue
            rf_id = rf.get("id", cut_dt.strftime("%Y%m%d%H%M"))
            t_label = rf.get("tier_label") or "退票节点"
            fee_pct = int(rf.get("fee_percent") or 0)
            if status == "purchased":
                summary_txt = f"【退票截止·{fee_pct}%费率】{artist}（{city}站）"
                alarm_trig = "-PT2H"
                alarm_desc = f"2小时后到达退票节点（{t_label}），如行程有变请及时处理！"
            elif rf.get("expect_return_drop", True) and status in ("upcoming_drop", "waiting_round2", "announced"):
                summary_txt = f"【回流票狙击】{artist}（{city}站·{t_label}）"
                alarm_trig = "-PT10M"
                alarm_desc = f"10分钟后迎退票截止线（{t_label}），大麦/猫眼极易释放回流余票，请准备刷新！"
            else:
                continue

            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:liveecho-refund-{cid}-{rf_id}@concert-tracker.local",
                    f"DTSTAMP:{now_utc}",
                    f"DTSTART;TZID=Asia/Shanghai:{cut_dt.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID=Asia/Shanghai:{(cut_dt + datetime.timedelta(minutes=30)).strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{_ics_escape(summary_txt)}",
                    f"LOCATION:{_ics_escape(platform)}",
                    f"DESCRIPTION:{_ics_escape(f'{t_label} · 手续费 {fee_pct}% · {ticket_url}')}",
                    "BEGIN:VALARM",
                    f"TRIGGER:{alarm_trig}",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(alarm_desc)}",
                    "END:VALARM",
                    "END:VEVENT",
                ]
            )

        # 3. Cross-City 12306 High-Speed Rail 15-Day Pre-Sale Reminder
        rail_plan = compute_12306_plan(home_city, concert)
        if rail_plan.get("is_cross_city") and not rail_plan.get("rail_booked") and status != "attended":
            rail_dt = _parse_local_shanghai_dt(rail_plan["outbound_12306_sale_time"])
            if rail_dt:
                r_home = rail_plan["home_city"]
                r_out = rail_plan["outbound_travel_date"]
                r_ret = rail_plan["return_12306_sale_time"][:10]
                r_corr = rail_plan["corridor"]
                r_tip = rail_plan.get("station_batch_tip", "")
                rail_desc = f"出行日期：{r_out}（返程购票日：{r_ret}）\n通道：{r_corr}" + (f"\n提示：{r_tip}" if r_tip else "")
                lines.extend(
                    [
                        "BEGIN:VEVENT",
                        f"UID:liveecho-12306-{cid}@concert-tracker.local",
                        f"DTSTAMP:{now_utc}",
                        f"DTSTART;TZID=Asia/Shanghai:{rail_dt.strftime('%Y%m%dT%H%M%S')}",
                        f"DTEND;TZID=Asia/Shanghai:{(rail_dt + datetime.timedelta(minutes=30)).strftime('%Y%m%dT%H%M%S')}",
                        f"SUMMARY:{_ics_escape(f'【12306抢高铁票】{r_home}→{city}（看{artist}）')}",
                        "LOCATION:铁路12306 App",
                        f"DESCRIPTION:{_ics_escape(rail_desc)}",
                        "BEGIN:VALARM",
                        "TRIGGER:-PT15M",
                        "ACTION:DISPLAY",
                        f"DESCRIPTION:{_ics_escape(f'12306 即将开售前往{city}的高铁票（{artist}演出跨城行程）！')}",
                        "END:VALARM",
                        "END:VEVENT",
                    ]
                )

        # 4. Concert showtime event
        show_dt = _parse_local_shanghai_dt(concert.get("show_time", ""))
        if show_dt:
            show_end = show_dt + datetime.timedelta(hours=3)
            loc = f"{city} {venue}".strip() or city
            show_desc = [
                f"艺人：{artist}",
                f"演出：{title}",
                f"地点：{loc}",
                f"票务：{platform}（{price}）",
                "出行提醒：中国大陆大型演出实行强实名制入场，请务必携带本人身份证原件！",
            ]
            if seat_note:
                show_desc.append(f"座位/票夹备注：{seat_note}")
            if ticket_url:
                show_desc.append(f"详情链接：{ticket_url}")

            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:liveecho-show-{cid}@concert-tracker.local",
                    f"DTSTAMP:{now_utc}",
                    f"DTSTART;TZID=Asia/Shanghai:{show_dt.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID=Asia/Shanghai:{show_end.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{_ics_escape(f'【演出】{artist} — {city} {venue}'.strip())}",
                    f"LOCATION:{_ics_escape(loc)}",
                    f"DESCRIPTION:{_ics_escape(chr(10).join(show_desc))}",
                    "BEGIN:VALARM",
                    "TRIGGER:-P1D",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(f'明天演出：{artist} {city}站，记得准备身份证原件！')}",
                    "END:VALARM",
                    "BEGIN:VALARM",
                    "TRIGGER:-PT3H",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(f'3小时后开演：{artist} @ {loc}')}",
                    "END:VALARM",
                    "END:VEVENT",
                ]
            )

    lines.append("END:VCALENDAR")
    folded = [_fold_ics_line(ln) for ln in lines]
    return "\r\n".join(folded) + "\r\n"


def _validate_smtp_host(host: str, port: int) -> None:
    if not host or port <= 0 or port > 65535:
        raise ValueError("Invalid SMTP host or port.")
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("Could not resolve SMTP hostname.")
    for info in infos:
        if _is_disallowed_ip(info[4][0]):
            raise ValueError("SMTP connections to private or loopback addresses are disallowed.")


def send_push_or_email_message(
    settings: dict[str, Any],
    subject: str,
    body: str,
    target_url: str = "",
    only_channel: str | None = None,
) -> dict[str, str]:
    """Dispatches a reminder across configured push/email channels and returns per-channel status."""
    outcomes: dict[str, str] = {}

    if settings.get("bark_url") and (only_channel in (None, "bark")):
        try:
            base = settings["bark_url"].rstrip("/")
            enc_title = urllib.parse.quote(subject, safe="")
            enc_body = urllib.parse.quote(body, safe="")
            bark_endpoint = f"{base}/{enc_title}/{enc_body}"
            params: dict[str, Any] = {"group": "现场回响", "level": "timeSensitive"}
            if target_url.startswith("https://"):
                params["url"] = target_url
            resp = safe_https_request("GET", bark_endpoint, params=params, timeout=6.0)
            outcomes["bark"] = "ok" if resp.status_code < 400 else f"http_{resp.status_code}"
        except Exception as exc:
            logger.warning("Bark delivery error: %s", type(exc).__name__)
            outcomes["bark"] = f"error: {exc}"

    if settings.get("serverchan_key") and (only_channel in (None, "serverchan")):
        try:
            sckey = settings["serverchan_key"].strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{6,96}", sckey):
                raise ValueError("Invalid ServerChan SendKey format.")
            sc_url = f"https://sctapi.ftqq.com/{sckey}.send"
            desp = f"{body}\n\n[直达链接]({target_url})" if target_url.startswith("https://") else body
            resp = safe_https_request("POST", sc_url, data={"title": subject, "desp": desp}, timeout=6.0)
            outcomes["serverchan"] = "ok" if resp.status_code < 400 else f"http_{resp.status_code}"
        except Exception as exc:
            logger.warning("ServerChan delivery error: %s", type(exc).__name__)
            outcomes["serverchan"] = f"error: {exc}"

    if settings.get("telegram_bot_token") and settings.get("telegram_chat_id") and (only_channel in (None, "telegram")):
        try:
            token = settings["telegram_bot_token"].strip()
            chat_id = settings["telegram_chat_id"].strip()
            tg_url = f"https://api.telegram.org/bot{urllib.parse.quote(token, safe=':')}/sendMessage"
            full_text = f"🎫 {subject}\n\n{body}" + (f"\n🔗 {target_url}" if target_url.startswith("https://") else "")
            resp = safe_https_request(
                "POST",
                tg_url,
                json_body={"chat_id": chat_id, "text": full_text, "disable_web_page_preview": True},
                timeout=6.0,
            )
            outcomes["telegram"] = "ok" if resp.status_code < 400 else f"http_{resp.status_code}"
        except Exception as exc:
            logger.warning("Telegram delivery error: %s", type(exc).__name__)
            outcomes["telegram"] = f"error: {exc}"

    if settings.get("webhook_url") and (only_channel in (None, "webhook")):
        try:
            wh_url = settings["webhook_url"].strip()
            full_text = f"【{subject}】\n{body}" + (f"\n{target_url}" if target_url.startswith("https://") else "")
            if "feishu.cn" in wh_url or "larksuite.com" in wh_url:
                payload: dict[str, Any] = {"msg_type": "text", "content": {"text": full_text}}
            elif "qyapi.weixin.qq.com" in wh_url or "oapi.dingtalk.com" in wh_url:
                payload = {"msgtype": "text", "text": {"content": full_text}}
            else:
                payload = {"text": full_text, "title": subject, "url": target_url}
            resp = safe_https_request("POST", wh_url, json_body=payload, timeout=6.0)
            outcomes["webhook"] = "ok" if resp.status_code < 400 else f"http_{resp.status_code}"
        except Exception as exc:
            logger.warning("Webhook delivery error: %s", type(exc).__name__)
            outcomes["webhook"] = f"error: {exc}"

    if settings.get("smtp_host") and settings.get("notify_email") and (only_channel in (None, "email")):
        try:
            host = settings["smtp_host"].strip()
            port = int(settings.get("smtp_port") or 587)
            _validate_smtp_host(host, port)
            msg = email.message.EmailMessage()
            sender = settings.get("smtp_user") or settings["notify_email"]
            msg["Subject"] = f"[现场回响] {subject}"
            msg["From"] = sender
            msg["To"] = settings["notify_email"]
            email_body = f"{body}\n\n直达链接：{target_url}" if target_url.startswith("https://") else body
            msg.set_content(email_body)

            ctx = ssl.create_default_context()
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=8.0, context=ctx) as smtp:
                    if settings.get("smtp_user") and settings.get("smtp_pass"):
                        smtp.login(settings["smtp_user"], settings["smtp_pass"])
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=8.0) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                    if settings.get("smtp_user") and settings.get("smtp_pass"):
                        smtp.login(settings["smtp_user"], settings["smtp_pass"])
                    smtp.send_message(msg)
            outcomes["email"] = "ok"
        except Exception as exc:
            logger.warning("Email delivery error: %s", type(exc).__name__)
            outcomes["email"] = f"error: {exc}"

    return outcomes


def run_reminder_check_cycle(
    db: Database,
    now: datetime.datetime | None = None,
    *,
    lookback_minutes: float = 2.0,
) -> int:
    """Dispatches due push/email alerts for ticket drops, returned-ticket windows, 12306 rail, and showtimes.

    `lookback_minutes` defaults to 2.0 for the 30-second live server loop, and can be widened (e.g. 22.0)
    for periodic serverless/GitHub Actions cron ticks; `reminder_logs` prevents duplicate deliveries.
    """
    ref_now = now or datetime.datetime.now(SHANGHAI_TZ)
    dispatched_count = 0
    win = max(2.0, float(lookback_minutes))

    for user_id in db.list_all_users_for_scheduler():
        settings = db.get_notification_settings_decrypted(user_id)
        has_any_channel = any(
            [
                settings.get("bark_url"),
                settings.get("serverchan_key"),
                settings.get("telegram_bot_token") and settings.get("telegram_chat_id"),
                settings.get("webhook_url"),
                settings.get("smtp_host") and settings.get("notify_email"),
            ]
        )
        if not has_any_channel:
            continue

        user = db.get_user_by_id(user_id) or {}
        pref_region = user.get("preferred_region", "all")
        pref_cities = set(user.get("preferred_cities") or [])
        home_city = user.get("home_city", "上海")

        concerts = db.list_concerts(user_id)
        for concert in concerts:
            c_status = concert.get("status")
            if c_status == "attended":
                continue
            if c_status == "discovered":
                if pref_region != "all" and concert.get("region") != pref_region:
                    continue
                if pref_cities and concert.get("city") not in pref_cities:
                    continue

            artist = concert["artist_name"]
            city = concert["city"]
            venue = concert.get("venue") or ""
            region_label = REGION_LABELS.get(concert.get("region", "other"), "")

            # 1. Ticket Rounds (抢票)
            if c_status != "purchased":
                for tr in concert.get("ticket_rounds") or []:
                    sale_dt = _parse_local_shanghai_dt(tr["sale_time"])
                    if not sale_dt:
                        continue
                    diff_min = (sale_dt - ref_now).total_seconds() / 60.0
                    for lead_m in settings.get("lead_minutes") or [60, 15, 5]:
                        lower_m = max(0.0, lead_m - win)
                        if lower_m <= diff_min <= (lead_m + 0.5):
                            event_key = f"drop:{concert['id']}:{tr['id']}:m{lead_m}"
                            if db.has_reminder_been_sent(user_id, event_key, "push_bundle"):
                                continue
                            subj = f"抢票倒计时 {max(1, int(round(diff_min)))} 分钟：{artist}（{city}站·{tr['round_label']}）"
                            body = (
                                f"演出：{concert['title']}\n"
                                f"城市：{city}（{region_label}） {venue}\n"
                                f"开票时间：{tr['sale_time']}（北京时间）\n"
                                f"平台：{tr.get('platform') or concert['platform']}\n"
                                f"请立即确认实名观演人与默认收货地址已勾选！"
                            )
                            res = send_push_or_email_message(
                                settings, subj, body, tr.get("booking_url") or concert.get("ticket_url", "")
                            )
                            if res:
                                db.record_reminder_sent(user_id, event_key, "push_bundle", "ok")
                                dispatched_count += 1

            # 2. Returned-Ticket Sniping & Refund Cutoff Alerts
            if settings.get("enable_return_sniper", True):
                for rf in concert.get("refund_tiers") or []:
                    cut_dt = _parse_local_shanghai_dt(rf["cutoff_time"])
                    if not cut_dt:
                        continue
                    diff_min = (cut_dt - ref_now).total_seconds() / 60.0
                    sniper_low = 6.0 if win <= 2.0 else max(0.0, 22.0 - win)
                    sniper_high = 11.0 if win <= 2.0 else max(11.0, win)
                    guard_low = min(108.0, 120.0 - win)
                    if c_status in ("upcoming_drop", "waiting_round2") and rf.get("expect_return_drop") and (sniper_low <= diff_min <= sniper_high):
                        event_key = f"sniper:{concert['id']}:{rf['id']}"
                        if not db.has_reminder_been_sent(user_id, event_key, "push_bundle"):
                            mins_txt = max(1, int(round(diff_min)))
                            subj = f"回流票狙击预警（{mins_txt}分钟后）：{artist}（{city}站）"
                            body = f"退票节点「{rf['tier_label']}」将于 {rf['cutoff_time']} 截止，票务平台即将释放退票回流库存，请立即蹲守刷新！"
                            res = send_push_or_email_message(settings, subj, body, concert.get("ticket_url", ""))
                            if res:
                                db.record_reminder_sent(user_id, event_key, "push_bundle", "ok")
                                dispatched_count += 1
                    elif c_status == "purchased" and int(rf.get("fee_percent") or 0) < 100 and (guard_low <= diff_min <= 122.0):
                        event_key = f"refund_guard:{concert['id']}:{rf['id']}"
                        if not db.has_reminder_been_sent(user_id, event_key, "push_bundle"):
                            subj = f"退票截止提醒（2小时后）：{artist}（{city}站·{rf['tier_label']}）"
                            body = f"你已购票的场次将于 {rf['cutoff_time']} 跨过「{rf['tier_label']}」，若行程有变动请及时确认。"
                            res = send_push_or_email_message(settings, subj, body, concert.get("ticket_url", ""))
                            if res:
                                db.record_reminder_sent(user_id, event_key, "push_bundle", "ok")
                                dispatched_count += 1

            # 3. 12306 High-Speed Rail Reminder
            if settings.get("enable_12306_reminders", True):
                rail = compute_12306_plan(home_city, concert)
                if rail.get("is_cross_city") and not rail.get("rail_booked"):
                    r_dt = _parse_local_shanghai_dt(rail["outbound_12306_sale_time"])
                    if r_dt:
                        diff_min = (r_dt - ref_now).total_seconds() / 60.0
                        rail_low = 9.0 if win <= 2.0 else max(0.0, 22.0 - win)
                        rail_high = 16.0 if win <= 2.0 else max(16.0, win)
                        if rail_low <= diff_min <= rail_high:
                            event_key = f"12306:{concert['id']}:{rail['outbound_12306_sale_time'][:10]}"
                            if not db.has_reminder_been_sent(user_id, event_key, "push_bundle"):
                                subj = f"12306 高铁开售提醒：{home_city}→{city}（看{artist}）"
                                body = (
                                    f"前往 {city} 观看 {artist}（出行日 {rail['outbound_travel_date']}）的火车票今日开售！\n"
                                    f"{rail.get('station_batch_tip', '')}"
                                ).strip()
                                res = send_push_or_email_message(settings, subj, body)
                                if res:
                                    db.record_reminder_sent(user_id, event_key, "push_bundle", "ok")
                                    dispatched_count += 1

            # 4. Showtime (开演)
            show_dt = _parse_local_shanghai_dt(concert["show_time"])
            if show_dt:
                diff_hr = (show_dt - ref_now).total_seconds() / 3600.0
                hr_win = max(0.25, win / 60.0)
                for lead_h in settings.get("show_lead_hours") or [24, 3]:
                    if max(0.05, lead_h - hr_win) <= diff_hr <= (lead_h + 0.05):
                        event_key = f"show:{concert['id']}:h{lead_h}"
                        if db.has_reminder_been_sent(user_id, event_key, "push_bundle"):
                            continue
                        subj = f"开演提醒（{lead_h}小时后）：{artist} — {city}站"
                        body = (
                            f"演出：{concert['title']}\n"
                            f"时间：{concert['show_time']}\n"
                            f"场馆：{city} {venue}\n"
                            f"入场必带：本人实体身份证原件！"
                        )
                        res = send_push_or_email_message(settings, subj, body, concert.get("ticket_url", ""))
                        if res:
                            db.record_reminder_sent(user_id, event_key, "push_bundle", "ok")
                            dispatched_count += 1

    return dispatched_count
