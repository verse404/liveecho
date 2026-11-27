(function () {
  "use strict";

  // Zero-server static runtime shim for GitHub Pages / Cloudflare Pages deployments.
  // Intercepts LiveEcho's /api/public/* requests and fulfills them locally using ./data/showcase.json.

  const origFetch = window.fetch ? window.fetch.bind(window) : null;
  let staticDataCache = null;
  let staticDataPromise = null;

  const STATION_BATCH_TIPS = {
    "北京": "北京西 08:00 / 北京南 12:30 / 北京朝阳 10:00",
    "上海": "上海虹桥 13:30 / 上海站 14:30 / 上海南 15:30",
    "广州": "广州南 10:00 / 广州东 11:30 / 广州白云 12:00",
    "深圳": "深圳北 09:00 / 福田 14:00 / 深圳站 09:30",
    "杭州": "杭州东 10:30 / 杭州西 10:30",
    "南京": "南京南 08:00 / 南京站 08:00",
    "成都": "成都东 09:00 / 成都南 09:00",
    "重庆": "重庆北 09:30 / 重庆西 09:30",
    "武汉": "武汉站 12:00 / 汉口 12:00",
    "西安": "西安北 10:30 / 西安站 10:30",
    "香港": "香港西九龙 10:00（跨境高铁请预留 45 分钟通关）"
  };

  const TRAD_MAP = {
    "陳": "陈", "張": "张", "鄧": "邓", "樂": "乐", "隊": "队", "會": "会", "場": "场",
    "館": "馆", "體": "体", "育": "育", "演": "演", "唱": "唱", "時": "时", "間": "间",
    "票": "票", "價": "价", "開": "开", "發": "发", "售": "售", "優": "优", "先": "先",
    "購": "购", "退": "退", "無": "无", "條": "条", "件": "件", "紅": "红", "磡": "磡",
    "廣": "广", "東": "东", "萬": "万", "巡": "巡", "迴": "回", "關": "关", "於": "于",
    "銀": "银", "綜": "综", "藝": "艺", "啟": "启", "風": "风", "龍": "龙", "國": "国"
  };

  function normText(s) {
    return String(s || "").replace(
      /[陳張鄧樂隊會場館體時價開發售優先購無條件紅廣東萬迴關於銀綜藝啟風龍國]/g,
      (ch) => TRAD_MAP[ch] || ch
    );
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function addDaysStr(ymd, delta) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(ymd || "");
    if (!m) return "";
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + delta));
    return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
  }

  async function loadStaticData(forceReload) {
    if (staticDataCache && !forceReload) return staticDataCache;
    if (staticDataPromise && !forceReload) return staticDataPromise;
    if (!origFetch) throw new Error("Browser fetch API unavailable");

    const url = forceReload ? `./data/showcase.json?t=${Date.now()}` : "./data/showcase.json";
    staticDataPromise = origFetch(url, { headers: { Accept: "application/json" } })
      .then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status} loading static showcase data`);
        return resp.json();
      })
      .then((data) => {
        staticDataCache = data;
        staticDataPromise = null;
        return data;
      })
      .catch((err) => {
        staticDataPromise = null;
        throw err;
      });
    return staticDataPromise;
  }

  function compute12306Client(homeCity, concert) {
    const origin = (homeCity || "上海").trim();
    const dest = (concert.city || "").trim();
    if (!dest || origin === dest) {
      return { is_cross_city: false, home_city: origin, dest_city: dest };
    }
    const showDate = (concert.show_time || "").slice(0, 10);
    const outTravel = showDate;
    const retTravel = addDaysStr(showDate, 1);
    const outSale = addDaysStr(outTravel, -14);
    const retSale = addDaysStr(retTravel, -14);
    return {
      is_cross_city: true,
      home_city: origin,
      dest_city: dest,
      corridor: `${origin} ⇄ ${dest} 高铁/动车`,
      outbound_travel_date: outTravel,
      return_travel_date: retTravel,
      outbound_12306_sale_time: `${outSale} 08:00`,
      return_12306_sale_time: `${retSale} 08:00`,
      station_batch_tip: STATION_BATCH_TIPS[origin] || `${origin}始发站请于发车前第 15 天按起售点抢票`
    };
  }

  function matchVenueGuideClient(data, venue, title) {
    const hay = `${venue || ""} ${title || ""}`;
    for (const g of data.venue_guides || []) {
      if ((g.keywords || []).some((kw) => hay.includes(kw))) {
        return {
          venue_name: g.venue_name,
          best_seats: g.best_seats,
          avoid_tip: g.avoid_tip,
          transit_tip: g.transit_tip
        };
      }
    }
    return null;
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    const rad = (deg) => (deg * Math.PI) / 180;
    const p1 = rad(lat1);
    const p2 = rad(lat2);
    const dp = rad(lat2 - lat1);
    const dl = rad(lon2 - lon1);
    const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  function estimateBudgetClient(data, homeCity, concert) {
    const origin = (homeCity || "上海").trim() || "上海";
    const dest = (concert.city || "").trim() || "上海";
    const pt = String(concert.price_text || "");
    const nums = Array.from(new Set((pt.match(/\d{3,4}/g) || []).map(Number))).sort((a, b) => a - b);
    let ticketMid = 680;
    if (nums.length === 1) ticketMid = nums[0];
    else if (nums.length === 2) ticketMid = Math.round((nums[0] + nums[1]) / 2);
    else if (nums.length > 2) ticketMid = nums[Math.floor(nums.length / 2)];
    if (/HK|港币|MOP/i.test(pt)) ticketMid = Math.round(ticketMid * 0.92);
    ticketMid = Math.max(180, Math.min(3600, ticketMid));

    if (origin === dest) {
      return {
        is_cross_city: false,
        origin,
        destination: dest,
        hsr_hours_one_way: 0,
        hsr_roundtrip_yuan: 0,
        hotel_1night_yuan: 0,
        ticket_mid_yuan: ticketMid,
        total_weekend_yuan: ticketMid,
        transport_note: `同城观演（${origin}），无需跨城高铁与住宿`
      };
    }

    const findNode = (ct) => (data.city_map_nodes || []).find((n) => n.city === ct);
    const oNode = findNode(origin) || { lat: 31.23, lon: 121.47, tier: 1 };
    const dNode = findNode(dest) || { lat: 30.59, lon: 114.3, tier: 2 };
    const airKm = haversineKm(oNode.lat || 31.23, oNode.lon || 121.47, dNode.lat || 30.59, dNode.lon || 114.3);
    const railKm = Math.max(35, airKm * 1.18);
    const hours = Math.round(Math.max(0.3, Math.min(11.5, railKm / 225)) * 10) / 10;
    const oneWay = Math.round(Math.max(45, Math.min(1180, railKm * 0.45)) / 10) * 10;
    const roundtrip = oneWay * 2;
    const hotel = dNode.tier === 0 ? 820 : dNode.tier === 1 ? 460 : 340;
    return {
      is_cross_city: true,
      origin,
      destination: dest,
      hsr_hours_one_way: hours,
      hsr_roundtrip_yuan: roundtrip,
      hotel_1night_yuan: hotel,
      ticket_mid_yuan: ticketMid,
      total_weekend_yuan: ticketMid + roundtrip + hotel,
      transport_note: `高铁单程约 ${hours} 小时 · 往返二等座约 ¥${roundtrip} · 周边住宿参考 ¥${hotel}/晚`
    };
  }

  function enrichConcertList(data, homeCity) {
    return (data.concerts || []).map((c) => {
      const copy = JSON.parse(JSON.stringify(c));
      copy.rail_plan = compute12306Client(homeCity, copy);
      copy.trip_estimate = estimateBudgetClient(data, homeCity, copy);
      copy.venue_guide = matchVenueGuideClient(data, copy.venue, copy.title);
      return copy;
    });
  }

  function buildSearchLinks(artistName) {
    const q = encodeURIComponent(String(artistName || "").trim());
    return {
      damai: `https://search.damai.cn/search.htm?ctl=%E6%BC%94%E5%94%B1%E4%BC%9A&order=1&cty=&keyword=${q}`,
      showstart: `https://www.showstart.com/event/list?pageNo=1&pageSize=20&cityCode=0&keyword=${q}`,
      maoyan: `https://show.maoyan.com/qqw#/search/${q}`,
      moretickets: `https://www.moretickets.com/search/${q}`,
      livenation: "https://www.livenation.cn/",
      songkick: `https://www.songkick.com/search?query=${q}&type=artists`,
      weibo: `https://s.weibo.com/weibo?q=${encodeURIComponent(String(artistName || "").trim() + " 演唱会 中国 官宣")}`
    };
  }

  function resolvePreset(data, query) {
    const qLow = String(query || "").trim().toLowerCase();
    for (const p of data.presets || []) {
      const cands = [p.name].concat(p.aliases || []);
      if (cands.some((c) => c.toLowerCase() === qLow || (qLow.length >= 2 && c.toLowerCase().includes(qLow)))) {
        return p;
      }
    }
    return null;
  }

  function handleArtistPreview(data, q) {
    const clean = String(q || "").trim();
    const matched = resolvePreset(data, clean);
    const primary = matched
      ? {
          name: matched.name,
          aliases: matched.aliases || [],
          genre: matched.genre || "",
          region_origin: matched.region_origin || "",
          category: matched.category || "cn"
        }
      : { name: clean, aliases: [], genre: "中外现场艺人", region_origin: "", category: "cn" };

    const tokens = [primary.name.toLowerCase()].concat((primary.aliases || []).map((a) => String(a).toLowerCase()));
    const presales = [];
    for (const c of data.concerts || []) {
      const hay = `${c.artist_name || ""} ${c.title || ""}`.toLowerCase();
      if (!tokens.some((tk) => tk && hay.includes(tk))) continue;
      presales.push({
        city: c.city,
        venue: c.venue,
        title: c.title,
        show_time: c.show_time,
        presale_label: "官方在售 / 每日同步排期",
        presale_time: "",
        platform: c.platform || "秀动",
        data_source: c.data_source || "ShowStart 秀动每日快照",
        ticket_url: c.ticket_url
      });
    }
    const skSnap = (data.songkick_snapshots || {})[primary.name.toLowerCase()] || { china_events: [], global_events: [] };
    for (const ce of skSnap.china_events || []) {
      presales.push({
        city: ce.city,
        venue: ce.venue,
        title: ce.title,
        show_time: ce.show_time,
        presale_label: "Songkick 官方排期",
        presale_time: "",
        platform: "Songkick",
        data_source: "Songkick 官方每日快照",
        ticket_url: ce.ticket_url
      });
    }
    const cities = Array.from(new Set(presales.map((p) => p.city).filter(Boolean)));
    return {
      primary_profile: primary,
      concerts: [],
      global_concerts: skSnap.global_events || [],
      live_sources_checked: ["ShowStart 秀动每日快照", "Songkick 全球排期每日快照"],
      fetched_at: data.live_fetched_at || "",
      upcoming_presales: presales,
      upcoming_cities: cities,
      search_links: buildSearchLinks(primary.name)
    };
  }

  function parseAnnouncementClient(data, rawText, homeCity) {
    const text = normText(rawText || "");
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const firstLine = lines[0] || "演出通告";

    let artist = "";
    for (const p of data.presets || []) {
      const cands = [p.name].concat(p.aliases || []);
      if (cands.some((c) => c && text.toLowerCase().includes(c.toLowerCase()))) {
        artist = p.name;
        break;
      }
    }
    if (!artist) {
      const mArt = /(?:官宣|重磅|举办|演员[：:])\s*】?\s*([A-Za-z0-9\u4e00-\u9fa5·\- ]{2,24})/.exec(text);
      artist = mArt ? mArt[1].trim().split(/[ 202（(「]/)[0] : "待确认艺人";
    }

    let city = "上海";
    for (const ct of Object.keys(data.city_to_region || {})) {
      if (text.includes(ct)) {
        city = ct;
        break;
      }
    }

    const mVenue = /(?:演出场馆|演出场所|场馆|地点)[：:]\s*(.+)/.exec(text);
    const venue = mVenue ? mVenue[1].replace(/^\[[^\]]+\]/, "").trim() : "场馆待公布";

    const mPrice = /(?:票价|票档)[：:]\s*(.+)/.exec(text);
    const priceText = mPrice ? mPrice[1].trim() : "票价待官宣";

    const mApp = /([京津沪渝冀晋辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云陕甘青宁新港澳]文旅[许审备字]〔\d{4}〕(?:涉外)?\d+号)/.exec(text);
    const approvalDoc = mApp ? mApp[1] : "";

    const platform = /Live Nation/i.test(text)
      ? "Live Nation"
      : /Cityline/i.test(text)
        ? "Cityline"
        : /城市售票|URBTIX/i.test(text)
          ? "城市售票网"
          : /秀动/.test(text)
            ? "秀动"
            : /猫眼/.test(text)
              ? "猫眼"
              : /纷玩岛/.test(text)
                ? "纷玩岛"
                : approvalDoc
                  ? "文旅局公示"
                  : "大麦";

    const mShow = /(?:演出时间|举办日期|时间)[：:]\s*(\d{4})[年\-\/.](\d{1,2})[月\-\/.](\d{1,2})日?(?:[－\-~至](\d{1,2})日?)?(?:\s+(\d{1,2}:\d{2}))?/.exec(text);
    const dates = [];
    if (mShow) {
      const y = mShow[1];
      const mo = pad2(mShow[2]);
      const d1 = Number(mShow[3]);
      const d2 = mShow[4] ? Number(mShow[4]) : d1;
      const hm = mShow[5] || "19:30";
      for (let d = d1; d <= Math.min(d2, d1 + 5); d++) {
        dates.push(`${y}-${mo}-${pad2(d)} ${hm}`);
      }
    } else {
      dates.push("2026-12-20 19:30");
    }

    const rounds = [];
    const roundRe = /(优先购|正式开票|正式预售|公开发售|一开|二开)[^0-9\n]{0,10}(\d{4})[年\-\/.](\d{1,2})[月\-\/.](\d{1,2})日?\s*(\d{1,2}:\d{2})(?:[（(]([^）)]+)[）)])?/g;
    let rm;
    while ((rm = roundRe.exec(text)) !== null) {
      rounds.push({
        round_label: rm[1],
        sale_time: `${rm[2]}-${pad2(rm[3])}-${pad2(rm[4])} ${rm[5]}`,
        platform: rm[6] || platform,
        booking_url: ""
      });
    }

    const refunds = [];
    if (/48小时.*无条件退票/.test(text) && rounds.length) {
      const baseDate = rounds[0].sale_time.slice(0, 10);
      refunds.push({
        tier_label: "48h无条件退票回流窗口",
        cutoff_time: `${addDaysStr(baseDate, 2)} ${rounds[0].sale_time.slice(11)}`,
        fee_percent: 0,
        expect_return_drop: true
      });
    }

    const mUrl = /(https:\/\/[^\s]+)/.exec(text);
    const items = dates.map((dt, idx) => {
      const item = {
        id: 8000 + Math.floor(Math.random() * 1000) + idx,
        artist_name: artist,
        title:
          dates.length > 1
            ? `${firstLine.replace(/^【[^】]+】/, "").trim()}（第 ${idx + 1} 场）`
            : firstLine.replace(/^【[^】]+】/, "").trim(),
        city,
        region: (data.city_to_region || {})[city] || "other",
        venue,
        show_time: dt,
        price_text: priceText,
        platform,
        ticket_url: mUrl ? mUrl[1] : "",
        status: approvalDoc && !rounds.length ? "approved_pending" : "upcoming_drop",
        approval_doc_no: approvalDoc,
        approval_source: approvalDoc ? "省市文旅部门公示" : "",
        ticket_rounds: rounds,
        refund_tiers: refunds
      };
      item.rail_plan = compute12306Client(homeCity, item);
      item.trip_estimate = estimateBudgetClient(data, homeCity, item);
      item.venue_guide = matchVenueGuideClient(data, item.venue, item.title);
      return item;
    });

    return {
      summary: `纯浏览器本地解析完成：识别出 ${items.length} 场演出（${artist} · ${city}站）`,
      items
    };
  }

  function sanitizeIcsText(val) {
    return String(val || "")
      .replace(/\\/g, "\\\\")
      .replace(/\r?\n/g, "\\n")
      .replace(/,/g, "\\,")
      .replace(/;/g, "\\;");
  }

  function toIcsStamp(dtStr) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[\sT](\d{2}):(\d{2}))?/.exec((dtStr || "").trim());
    if (!m) return "20261220T113000Z";
    const d = new Date(
      Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), (m[4] ? Number(m[4]) : 19) - 8, m[5] ? Number(m[5]) : 30)
    );
    return `${d.getUTCFullYear()}${pad2(d.getUTCMonth() + 1)}${pad2(d.getUTCDate())}T${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}00Z`;
  }

  function generateIcsClient(concerts) {
    const lines = [
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//LiveEcho//China Concert Tracker Static//ZH"
    ];
    for (const c of concerts || []) {
      const uidBase = `le-${c.id || Math.floor(Math.random() * 1e6)}`;
      lines.push(
        "BEGIN:VEVENT",
        `UID:${uidBase}-show@liveecho`,
        `DTSTART:${toIcsStamp(c.show_time)}`,
        `SUMMARY:${sanitizeIcsText(`[演出] ${c.artist_name} ${c.city}站`)}`,
        `LOCATION:${sanitizeIcsText(`${c.city} ${c.venue || ""}`)}`,
        `DESCRIPTION:${sanitizeIcsText(`${c.title || ""} (${c.price_text || ""})`)}`,
        "END:VEVENT"
      );
      for (const r of c.ticket_rounds || []) {
        lines.push(
          "BEGIN:VEVENT",
          `UID:${uidBase}-sale-${(r.sale_time || "").replace(/\D/g, "")}@liveecho`,
          `DTSTART:${toIcsStamp(r.sale_time)}`,
          `SUMMARY:${sanitizeIcsText(`[开票抢票] ${c.artist_name} ${c.city}站 (${r.round_label})`)}`,
          `DESCRIPTION:${sanitizeIcsText(`平台：${r.platform || c.platform}`)}`,
          "BEGIN:VALARM",
          "TRIGGER:-PT15M",
          "ACTION:DISPLAY",
          `DESCRIPTION:${sanitizeIcsText(`${c.artist_name} 即将于 15 分钟后开票！`)}`,
          "END:VALARM",
          "END:VEVENT"
        );
      }
    }
    lines.push("END:VCALENDAR");
    return lines.join("\r\n");
  }

  function triggerIcsDownload(icsText, filename) {
    const blob = new Blob([icsText], { type: "text/calendar;charset=utf-8" });
    const objUrl = URL.createObjectURL(blob);
    const dl = document.createElement("a");
    dl.href = objUrl;
    dl.download = filename;
    document.body.appendChild(dl);
    dl.click();
    document.body.removeChild(dl);
    window.setTimeout(() => URL.revokeObjectURL(objUrl), 2000);
  }

  window.fetch = async function (input, init) {
    const urlStr = typeof input === "string" ? input : (input && input.url) || "";

    if (urlStr.startsWith("/api/public/showcase")) {
      const qs = new URLSearchParams(urlStr.split("?")[1] || "");
      const home = qs.get("home_city") || "上海";
      const wantRefresh = qs.get("refresh") === "1";
      const data = await loadStaticData(wantRefresh);
      const payload = {
        authenticated: false,
        username: "",
        followed_artists: [],
        csrf_token: "static-site-mode",
        home_city: home,
        regions: data.regions,
        city_map_nodes: data.city_map_nodes,
        venue_guides: data.venue_guides,
        culture_portals: data.culture_portals,
        presets: data.presets,
        concerts: enrichConcertList(data, home),
        festival_demo: data.festival_demo || null,
        local_ocr_available: false,
        vision_ocr_available: false,
        live_fetched_at: data.live_fetched_at || "",
        live_sources: data.live_sources || []
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" }
      });
    }

    if (urlStr.startsWith("/api/public/artist-preview")) {
      const qs = new URLSearchParams(urlStr.split("?")[1] || "");
      const data = await loadStaticData(false);
      const bundle = handleArtistPreview(data, qs.get("q") || "");
      return new Response(JSON.stringify(bundle), {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" }
      });
    }

    if (urlStr === "/api/public/parse-preview") {
      const data = await loadStaticData(false);
      const body = JSON.parse((init && init.body) || "{}");
      const parsed = parseAnnouncementClient(data, body.text || "", body.home_city || "上海");
      return new Response(JSON.stringify(parsed), {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" }
      });
    }

    if (urlStr === "/api/public/parse-ics") {
      const data = await loadStaticData(false);
      const body = JSON.parse((init && init.body) || "{}");
      const parsed = parseAnnouncementClient(data, body.text || "", body.home_city || "上海");
      const ics = generateIcsClient(parsed.items || []);
      return new Response(ics, {
        status: 200,
        headers: { "Content-Type": "text/calendar; charset=utf-8" }
      });
    }

    if (urlStr === "/api/public/parse-festival-photo") {
      return new Response(
        JSON.stringify({
          error:
            "当前为纯静态零服务器版本（GitHub Pages / Cloudflare Pages），不含后端 OCR 引擎。请直接粘贴文字或手动补充时段，或运行本地/Render 后端以使用免费离线识图。"
        }),
        { status: 400, headers: { "Content-Type": "application/json; charset=utf-8" } }
      );
    }

    if (origFetch) return origFetch(input, init);
    return new Response(JSON.stringify({ error: "Static mode: backend endpoint unavailable" }), { status: 503 });
  };

  document.addEventListener("click", async (ev) => {
    const rootLink = ev.target && ev.target.closest ? ev.target.closest('a[href="/"]') : null;
    if (rootLink) {
      ev.preventDefault();
      const target = document.getElementById("watchlist");
      if (target) target.scrollIntoView({ behavior: "smooth" });
      return;
    }
    const a = ev.target && ev.target.closest ? ev.target.closest('a[href^="/api/public/showcase-ics"]') : null;
    if (!a) return;
    ev.preventDefault();
    const data = await loadStaticData(false);
    const href = a.getAttribute("href") || "";
    const qs = new URLSearchParams(href.split("?")[1] || "");
    const idParam = qs.get("id") || "all";
    const artistsParam = qs.get("artists") || "";
    const all = data.concerts || [];
    let selected = all;
    if (artistsParam) {
      const wanted = artistsParam
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
      selected = all.filter((c) => wanted.some((w) => `${c.artist_name} ${c.title}`.toLowerCase().includes(w)));
      if (!selected.length) selected = all;
    } else if (idParam !== "all") {
      const hit = all.filter((c) => String(c.id) === String(idParam));
      if (hit.length) selected = hit;
    }
    const icsText = generateIcsClient(selected);
    const fname = artistsParam ? "liveecho-favorite-presales.ics" : `liveecho-concert-${idParam}.ics`;
    triggerIcsDownload(icsText, fname);
  });
})();
