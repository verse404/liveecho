# 现场回响 LiveEcho — China Concert, Festival & Ticket-Drop Tracker

**LiveEcho (`现场回响`)** is a full-stack China concert, music festival, and ticket-drop tracking web application and editorial portal—covering the entire concertgoer lifecycle from early government `文旅局` approval filings to multi-round `抢票` countdowns, `回流票` sniping, cross-city `12306` high-speed rail reminders, and a collectible `票根纪念墙`.

It ships with **two integrated web experiences**:
- **Editorial Website Portal (`/website`)**: Zero-login nationwide & HK/Macau tour showcase, live artist search, ticking on-sale/refund-drop board, interactive festival single-day & stage-clash advisor, `12306` rail date calculator, and a live Smart Paste parser studio.
- **Personal Concert Vault (`/`)**: Authenticated multi-user tracker with automated background tour discovery, poster OCR import, `.ics` calendar sync, browser desktop notifications, encrypted push channels, and portable JSON backups.

---

## Key Features

1. **Smart Announcement Paste (`智能粘贴官宣文案`)**: Parses Simplified & Traditional Chinese announcements from Weibo (`微博`), Damai (`大麦`), Maoyan (`猫眼`), ShowStart (`秀动`), Bilibili (`B站会员购`), Fenwandao (`纷玩岛`), HK/Macau/TW platforms (`Cityline`, `城市售票网`, `快达票`, `KKTIX`, `拓元`), provincial Culture Bureau filings, consecutive multi-night stadium dates (`12月19日-21日`), and multi-stage festival timetables.
2. **Tour Poster Screenshot / OCR Import (`长图官宣海报识图`)**: Drag-and-drop or `Ctrl+V` paste vertical tour posters (`PNG`/`JPG`/`WEBP` ≤ 5 MB) with magic-byte verification, Pillow pixel-level Content Disarm & Reconstruction (CDR) EXIF stripping, optional encrypted Gemini Vision OCR, and a built-in sample poster generator.
3. **Tiered Refund Cutoffs & Returned-Ticket Snipers (`阶梯退票截止线 & 回流票狙击`)**: Tracks `0% 无条件退` (48h post-sale), `20% 手续费`, and `停止退票` deadlines—alerting you 10 minutes before returned tickets (`回流票`) drop back into inventory or 2 hours before refund tiers expire on purchased tickets.
4. **Ministry of Culture Early-Bird Radar (`省市文旅局审批早鸟`)**: Tracks `已过审·待官宣` tours (`苏文旅许` / `粤文旅审` / `沪文旅许` / `京文旅许`) weeks ahead of official Weibo announcements so you can lock refundable hotels early.
5. **Music Festival Mode (`音乐节拼盘决策台`)**: Aggregates followed bands at the same festival (`草莓音乐节`, `迷笛`, etc.), recommends which single-day ticket (`单日票`) covers the most favorites, and warns about overlapping or midnight-crossing set-time clashes (`撞场预警`).
6. **Cross-City `12306` High-Speed Rail Planner (`跨城高铁开售联动`)**: Compares concert cities (including cross-border `香港西九龙站` and `澳门/珠海站`) against your home city and schedules T-15-day `12306` pre-sale reminders in-app, via push, and in RFC 5545 `.ics` calendars.
7. **Collectible Ticket-Stub Wall (`票根纪念墙与观演手账`)**: Tracks annual live-show statistics (attended count, unlocked cities, total spend, average venue acoustics rating), seat-view notes, and encore setlist memories.
8. **Automated Tour Radar & Triple-Channel Reminders**: Concurrent ShowStart (`秀动`) SSR + hardened RSS/Atom scanning, Apple Music CN + MusicBrainz artist alias lookup, RFC 5545 75-octet folded `.ics` calendar export/WebCal feed, Browser `Notification` pop-ups, and Fernet-encrypted **Bark (iOS) / Server酱 (WeChat) / Telegram / Feishu-WeCom-DingTalk Webhook / SMTP Email** alerts.

---

## Security Architecture

- **XSS & Strict Nonce CSP**: Zero `innerHTML`/`outerHTML` or inline styles; per-request cryptographic script nonces (`script-src 'self' 'nonce-...'`, `style-src 'self'`, `object-src 'none'`, `frame-ancestors 'self'`).
- **Session, Password & CSRF Hardening**: `bcrypt` (12 rounds) password hashing, SHA-256 hashed session tokens in SQLite (`HttpOnly; SameSite=Lax`, `__Host-` + `Secure` under TLS), 7-day TTL + 24h inactivity timeout, and Synchronizer/Double-Submit CSRF tokens on all `POST` endpoints.
- **SQLite Ownership Isolation & Encryption at Rest**: 100% parameterized SQL queries scoped by `user_id`; push & Vision API keys encrypted at rest with `Fernet` and masked in UI responses.
- **SSRF, XXE & Upload CDR Protection**: Outbound HTTPS requests validate resolved DNS IPs against private/loopback/link-local ranges on every redirect hop; XML DTD/entity declarations are rejected; uploaded posters undergo pixel-level CDR re-encoding outside the web root (`0600`) and download with `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`.

---

## Quick Start (Local)

Requires **Python 3.11+**. Core features require **zero external API keys**.

```bash
pip install -r requirements.txt
python3 -P server.py --host 127.0.0.1 --port 8788
```

- **Editorial Website Portal**: http://127.0.0.1:8788/website
- **Personal Concert Vault**: http://127.0.0.1:8788/

---

## Running Automated Tests

```bash
python3 -P -m unittest discover -s tests -t . -v
```

---

## Deployment Option 1 (Recommended for $0 / 0 Render Quota): Static-Only Hosting (GitHub Pages or Cloudflare Pages)

Want **literally 0 Render hours, 0 Turso database usage, and 0 secrets**? LiveEcho builds into a strict-CSP zero-server static bundle (`dist/`) with daily automated concert schedule updates and local browser persistence (`localStorage`) for your favorite artists, home city, theme, and custom ticket stubs:

### GitHub Pages (Free on Public Repositories)
1. Push this repository to a **Public** GitHub repository.
2. In GitHub, open **Settings → Pages → Build and deployment → Source** and select **GitHub Actions**.
3. The included `.github/workflows/deploy-github-pages.yml` workflow automatically builds `dist/` via `python3 scripts/build_static_site.py` on every push and refreshes live ShowStart + Songkick data **once daily at 08:00 Beijing Time** (~30 Actions runs/month; unlimited free on Public repos).

### Cloudflare Pages (Free on Both Public & Private Repositories)
1. Connect this GitHub repository (Public or **Private**) in **Cloudflare Dashboard → Workers & Pages → Create → Pages**.
2. Configure:
   - **Build command:** `pip install -r requirements.txt && python3 scripts/build_static_site.py --out-dir dist`
   - **Build output directory:** `dist`
3. Cloudflare Pages automatically applies `dist/_headers` (CSP, `X-Frame-Options`, `nosniff`, asset cache rules) with **unlimited free bandwidth** and **500 free builds/month**.

### Build Static Bundle Locally
```bash
python3 scripts/build_static_site.py --out-dir dist
```

---

## Deployment Option 2 (Full-Stack Personal Vault): Render Free + Turso + GitHub Actions

If you want multi-device **Personal Concert Vault (`/`)** login sync, server-side **Tesseract offline poster OCR**, and automated **Bark / Server酱 / Telegram / Email push reminders**:

1. **Create a Free Turso Cloud SQLite Database (`turso.tech` — 5 GB Free, No Card Required)**:
   - Sign in with GitHub at https://turso.tech, create a database named `liveecho` (pick region **Singapore `sin`** to match `render.yaml`), and generate a **database-scoped** token (`TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`).
   - Generate one shared 64-char encryption secret:
     ```bash
     python3 -c "import secrets; print(secrets.token_hex(32))"
     ```
2. **Deploy Web App on Render Free Tier (`render.yaml`)**:
   - In Render, click **New + → Blueprint**, select your `LiveEcho` GitHub repository, paste `CONCERT_TRACKER_SECRET_KEY`, `TURSO_DATABASE_URL`, and `TURSO_AUTH_TOKEN`, and click **Apply**.
   - Both `/` (Personal Concert Vault) and `/website` (Zero-Login Editorial Portal) go live over HTTPS, with `/api/healthz` reporting `"storage": "turso"`.
   - Uploaded tour posters are stored both in local cache and as CDR-sanitized PNG blobs inside Turso, so posters never disappear across container restarts.
3. **Optional Background Push Reminders via GitHub Actions (`.github/workflows/liveecho-cloud-cron.yml`)**:
   - Scheduled ticks are commented out by default so static-only deployments never waste Actions minutes.
   - To enable 30-minute background reminders + 6-hour tour radar against Turso (without waking Render), add `CONCERT_TRACKER_SECRET_KEY`, `TURSO_DATABASE_URL`, and `TURSO_AUTH_TOKEN` to **Settings → Secrets and variables → Actions** and uncomment the `schedule` lines in `.github/workflows/liveecho-cloud-cron.yml`.

### Docker (Self-Hosted / VPS)
```bash
docker build -t liveecho .
docker run --rm -p 8080:8080 \
  -e CONCERT_TRACKER_ENV=production \
  -e CONCERT_TRACKER_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  liveecho
```

---

## License

MIT License — see [LICENSE](./LICENSE).
