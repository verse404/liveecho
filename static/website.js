/* LiveEcho (现场回响) — Public Editorial Website Version Frontend v3.
 * Strictly XSS-safe & CSP-safe: DOM-API & createElementNS only, zero raw HTML string
 * injection, zero inline style attributes, zero native browser dialogs, sandbox-safe storage.
 */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  const PLAYGROUND_SAMPLES = [
    {
      label: "测试模板①：大麦单站 + 退票规则（仅测解析）",
      text: [
        "【官宣】草东没有派对 2026 专场演出（杭州站）",
        "演出时间：2026年12月19日 19:30",
        "演出场馆：杭州奥体中心体育馆",
        "票价：¥380 / 580 / 780 / 980元",
        "优先购开启：2026年11月28日 11:18（纷玩岛）",
        "正式开票时间：2026年11月29日 12:18（大麦）",
        "退票规则：开票后48小时内无条件退票（0%手续费）",
        "退票规则：2026年12月05日 12:00前退票收取20%手续费",
        "2026年12月15日 12:00停止退票",
        "https://www.damai.cn/",
      ].join("\n"),
    },
    {
      label: "测试模板②：香港红馆繁体连开（仅测解析）",
      text: [
        "【重磅】陳奕迅 FEAR AND DREAMS 世界巡迴演唱會（香港站）",
        "演出時間：2026年12月19日-21日 20:15",
        "演出場館：紅磡香港體育館",
        "票價：HK$1280 / 980 / 680",
        "信用卡優先購：2026年11月26日 10:00（Cityline）",
        "公開發售：2026年11月28日 10:00（城市售票網）",
        "開票後48小時內無條件退票",
        "https://www.urbtix.hk/",
      ].join("\n"),
    },
    {
      label: "测试模板③：省文旅局批文格式（仅测解析）",
      text: [
        "广东省文化和旅游厅关于准予举办邓紫棋2027巡回演唱会（广州站）的行政许可决定",
        "许可文号：粤文旅审〔2026〕2046号",
        "举办日期：2027年01月23日 19:00",
        "演出场所：广东奥林匹克体育中心体育场",
        "申请演出演员：邓紫棋",
        "https://dct.gd.gov.cn/",
      ].join("\n"),
    },
    {
      label: "测试模板④：音乐节双舞台时刻表（仅测解析）",
      text: [
        "2026广州超级草莓音乐节 全阵容时刻表公布！",
        "演出时间：2026年12月05日 13:30",
        "地点：[广州]南沙音乐秀场",
        "票价：¥368-658",
        "正式开票：2026年11月27日 11:18（秀动）",
        "2026年12月05日",
        "草莓舞台 19:30-20:15 新裤子",
        "爱舞台 19:50-20:35 落日飞车",
        "2026年12月06日",
        "草莓舞台 20:10-20:55 万能青年旅店",
        "https://www.showstart.com/",
      ].join("\n"),
    },
    {
      label: "测试模板⑤：涉外批文格式（仅测解析）",
      text: [
        "【重磅官宣】Imagine Dragons LOOM 世界巡回演唱会（深圳站）",
        "涉外批文：粤文旅审〔2026〕涉外1802号",
        "演出时间：2026年12月26日 19:30",
        "演出场馆：深圳大运中心体育场",
        "票价：¥380 / 580 / 880 / 1280 / 1680元",
        "Live Nation 优先购：2026年11月27日 11:00（大麦）",
        "正式预售开启：2026年11月28日 11:00（大麦）",
        "开票后48小时内无条件退票",
        "https://www.damai.cn/",
      ].join("\n"),
    },
  ];

  const DEFAULT_CITY_MAP_NODES = [
    { city: "长春", region: "north_nw", x: 598, y: 92, lx: -13, ly: 4, anchor: "end", tier: 2 },
    { city: "北京", region: "jjj", x: 494, y: 144, lx: 15, ly: -8, anchor: "start", tier: 1 },
    { city: "天津", region: "jjj", x: 524, y: 162, lx: 12, ly: 5, anchor: "start", tier: 2 },
    { city: "石家庄", region: "jjj", x: 462, y: 178, lx: -12, ly: 4, anchor: "end", tier: 2 },
    { city: "济南", region: "north_nw", x: 520, y: 198, lx: -12, ly: 4, anchor: "end", tier: 2 },
    { city: "青岛", region: "north_nw", x: 576, y: 196, lx: 12, ly: 4, anchor: "start", tier: 2 },
    { city: "郑州", region: "central", x: 462, y: 230, lx: -12, ly: 4, anchor: "end", tier: 2 },
    { city: "西安", region: "north_nw", x: 384, y: 236, lx: -12, ly: 4, anchor: "end", tier: 2 },
    { city: "南京", region: "jzh", x: 534, y: 252, lx: -14, ly: -4, anchor: "end", tier: 2 },
    { city: "合肥", region: "jzh", x: 506, y: 274, lx: -12, ly: 12, anchor: "end", tier: 2 },
    { city: "苏州", region: "jzh", x: 574, y: 254, lx: 0, ly: -13, anchor: "middle", tier: 2 },
    { city: "上海", region: "jzh", x: 608, y: 272, lx: 16, ly: 4, anchor: "start", tier: 1 },
    { city: "杭州", region: "jzh", x: 572, y: 298, lx: -13, ly: 6, anchor: "end", tier: 2 },
    { city: "宁波", region: "jzh", x: 608, y: 318, lx: 12, ly: 5, anchor: "start", tier: 2 },
    { city: "武汉", region: "central", x: 462, y: 284, lx: -14, ly: 4, anchor: "end", tier: 2 },
    { city: "长沙", region: "central", x: 456, y: 324, lx: -12, ly: 4, anchor: "end", tier: 2 },
    { city: "成都", region: "cy", x: 302, y: 290, lx: -15, ly: 4, anchor: "end", tier: 2 },
    { city: "重庆", region: "cy", x: 354, y: 312, lx: 14, ly: 5, anchor: "start", tier: 2 },
    { city: "厦门", region: "fujian", x: 558, y: 356, lx: 12, ly: 4, anchor: "start", tier: 2 },
    { city: "广州", region: "gba", x: 468, y: 374, lx: -15, ly: -4, anchor: "end", tier: 1 },
    { city: "深圳", region: "gba", x: 506, y: 388, lx: 16, ly: -2, anchor: "start", tier: 1 },
    { city: "香港", region: "gba", x: 524, y: 416, lx: 16, ly: 6, anchor: "start", tier: 0 },
    { city: "澳门", region: "gba", x: 472, y: 416, lx: -15, ly: 6, anchor: "end", tier: 0 },
    { city: "澄迈", region: "gba", x: 416, y: 424, lx: -12, ly: 4, anchor: "end", tier: 2 },
  ];

  // Zero fictional attended ticket stubs — users add their own real concerts via the PNG Stub Studio
  const ARCHIVE_STUBS = [];

  function safeReadPref(key, fallback) {
    try {
      const val = window.localStorage.getItem(key);
      return val !== null ? val : fallback;
    } catch (_e) {
      return fallback;
    }
  }

  function safeWritePref(key, val) {
    try {
      window.localStorage.setItem(key, String(val));
    } catch (_e) {
      // Safe no-op under restricted sandbox origins
    }
  }

  function readUrlParam(name) {
    try {
      const params = new URLSearchParams(window.location.search || "");
      return params.get(name);
    } catch (_e) {
      return null;
    }
  }

  function readInitialFavorites() {
    const raw = readUrlParam("fav");
    if (raw !== null) {
      return raw.split(",").map((s) => s.trim()).filter(Boolean);
    }
    const saved = safeReadPref("liveecho_favorites", "");
    if (saved) {
      return saved.split(",").map((s) => s.trim()).filter(Boolean);
    }
    return [];
  }

  function readSavedStubs() {
    try {
      const raw = safeReadPref("liveecho_stubs_v1", "");
      if (!raw) return ARCHIVE_STUBS.slice();
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter((s) => s && typeof s === "object" && typeof s.artist === "string").slice(0, 50);
      }
    } catch (_e) {
      // Ignore malformed local preference
    }
    return ARCHIVE_STUBS.slice();
  }

  function persistSavedStubs() {
    try {
      safeWritePref("liveecho_stubs_v1", JSON.stringify(siteState.archiveStubs.slice(0, 50)));
    } catch (_e) {
      // Ignore quota or sandbox errors
    }
  }

  function readInitialTheme() {
    const q = readUrlParam("theme");
    if (q === "dark" || q === "light") return q;
    const saved = safeReadPref("liveecho_theme", "");
    if (saved === "dark" || saved === "light") return saved;
    return "light";
  }

  function readInitialHomeCity() {
    const q = (readUrlParam("home") || "").trim();
    const valid = ["上海", "北京", "广州", "深圳", "杭州", "南京", "成都", "重庆", "武汉", "西安", "香港"];
    if (valid.includes(q)) return q;
    const saved = safeReadPref("liveecho_home_city", "上海");
    return valid.includes(saved) ? saved : "上海";
  }

  const nowShanghai = new Date(Date.now() + 8 * 3600 * 1000);

  const siteState = {
    csrfToken: "",
    authenticated: false,
    username: "",
    theme: readInitialTheme(),
    homeCity: readInitialHomeCity(),
    selectedCategory: "all",
    selectedRegion: "all",
    directoryView: "list", // "list" | "calendar" | "map"
    directoryQuery: "",
    directoryExpandedAll: false,
    onlyFavorites: false,
    expandedConcertId: 901,
    spotlightIndex: 0,
    selectedMapCity: "",
    calYear: nowShanghai.getUTCFullYear(),
    calMonth: nowShanghai.getUTCMonth(), // 0-indexed
    calMonthAutoPicked: false,
    selectedCalDate: "",
    regions: {},
    cityMapNodes: DEFAULT_CITY_MAP_NODES,
    venueGuides: [],
    presets: [],
    culturePortals: [],
    concerts: [],
    festivalDemo: null,
    liveFetchedAt: "",
    liveSources: [],
    archiveStubs: readSavedStubs(),
    favoriteArtists: new Set(readInitialFavorites()),
    browserAlertsEnabled: false,
    alertLeadMinutes: 15,
    firedAlertKeys: new Set(),
    lastSearchedBundle: null,
    lastParsedItems: [],
    lastParsedRawText: "",
    selectedFestivalKey: "",
    selectedFestivalBands: new Set(),
    selectedFestivalBandsByKey: {},
    customFestivalSlots: {},
    festivalPasteDrafts: {},
    festivalPhotoState: {},
    localOcrAvailable: false,
    visionOcrAvailable: false,
    sessionVisionApiKey: "",
    lastShowcaseLoadMs: 0,
    prepChecks: {},
  };

  function syncStateToUrl() {
    const list = Array.from(siteState.favoriteArtists);
    safeWritePref("liveecho_favorites", list.join(","));
    try {
      const url = new URL(window.location.href);
      if (list.length) {
        url.searchParams.set("fav", list.join(","));
      } else {
        url.searchParams.set("fav", "");
      }
      url.searchParams.set("home", siteState.homeCity);
      if (siteState.theme === "dark") {
        url.searchParams.set("theme", "dark");
      } else {
        url.searchParams.delete("theme");
      }
      window.history.replaceState(null, "", url.toString());
    } catch (_e) {
      // Safe no-op in sandboxed null-origin contexts
    }
  }

  function applyTheme(theme) {
    siteState.theme = theme === "dark" ? "dark" : "light";
    if (siteState.theme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    safeWritePref("liveecho_theme", siteState.theme);
    const btn = document.getElementById("btn-theme-toggle");
    if (btn) {
      btn.textContent = siteState.theme === "dark" ? "☀ 宣纸日光" : "◐ 黑胶暗夜";
    }
    syncStateToUrl();
  }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "className") {
          node.className = String(v);
        } else if (k === "text") {
          node.textContent = String(v);
        } else if (k.startsWith("on") && typeof v === "function") {
          node.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (v === true) {
          node.setAttribute(k, "");
        } else {
          node.setAttribute(k, String(v));
        }
      }
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === "string" || typeof child === "number") {
        node.appendChild(document.createTextNode(String(child)));
      } else {
        node.appendChild(child);
      }
    }
    return node;
  }

  function svgEl(tag, attrs, ...children) {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "className") {
          node.setAttribute("class", String(v));
        } else if (k === "text") {
          node.textContent = String(v);
        } else if (k.startsWith("on") && typeof v === "function") {
          node.addEventListener(k.slice(2).toLowerCase(), v);
        } else {
          node.setAttribute(k, String(v));
        }
      }
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === "string" || typeof child === "number") {
        node.appendChild(document.createTextNode(String(child)));
      } else {
        node.appendChild(child);
      }
    }
    return node;
  }

  function setChildren(parent, ...items) {
    if (!parent) return;
    const flatNodes = items
      .flat(Infinity)
      .filter((x) => x !== null && x !== undefined && x !== false)
      .map((x) => (typeof x === "string" || typeof x === "number" ? document.createTextNode(String(x)) : x));
    parent.replaceChildren(...flatNodes);
  }

  function showSiteToast(msg, isErr) {
    const stack = document.getElementById("site-toast-stack");
    if (!stack) return;
    while (stack.children.length >= 2) {
      stack.removeChild(stack.firstChild);
    }
    const item = el("div", {
      className: isErr ? "site-toast is-error" : "site-toast",
      text: msg,
    });
    stack.appendChild(item);
    window.setTimeout(() => {
      if (item.parentNode) item.parentNode.removeChild(item);
    }, 3400);
  }

  function openSiteModal(title, bodyNodes, footNodes) {
    const overlay = document.getElementById("site-modal-overlay");
    const titleEl = document.getElementById("site-modal-title");
    const bodyEl = document.getElementById("site-modal-body");
    const footEl = document.getElementById("site-modal-foot");
    if (!overlay || !titleEl || !bodyEl || !footEl) return;
    titleEl.textContent = title;
    setChildren(bodyEl, bodyNodes);
    setChildren(footEl, footNodes);
    overlay.hidden = false;
  }

  function closeSiteModal() {
    const overlay = document.getElementById("site-modal-overlay");
    if (overlay) overlay.hidden = true;
  }

  function parseShanghaiMs(dtStr) {
    if (!dtStr) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[\sT](\d{2}):(\d{2}))?/.exec(dtStr.trim());
    if (!m) return null;
    return Date.UTC(
      Number(m[1]),
      Number(m[2]) - 1,
      Number(m[3]),
      (m[4] ? Number(m[4]) : 19) - 8,
      m[5] ? Number(m[5]) : 30,
      0
    );
  }

  function formatRailSaleStatus(saleTimeStr) {
    if (!saleTimeStr) return "见 12306 官网";
    const ms = parseShanghaiMs(saleTimeStr);
    if (ms && ms <= Date.now()) {
      return "已开售（可立即购票）";
    }
    return `${saleTimeStr} 起售`;
  }

  function formatCountdown(targetMs, nowMs) {
    const diffSec = Math.floor((targetMs - nowMs) / 1000);
    if (diffSec <= -1800) return "本轮已结束";
    if (diffSec <= 0) return "正在放票中！";
    const d = Math.floor(diffSec / 86400);
    const h = String(Math.floor((diffSec % 86400) / 3600)).padStart(2, "0");
    const m = String(Math.floor((diffSec % 3600) / 60)).padStart(2, "0");
    const s = String(diffSec % 60).padStart(2, "0");
    return d > 0 ? `${d}天 ${h}:${m}:${s}` : `${h}:${m}:${s}`;
  }

  function formatClockNow() {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date());
  }

  function hhmmToMinutes(str) {
    const m = /^(\d{1,2}):(\d{2})$/.exec((str || "").trim());
    if (!m) return null;
    return Number(m[1]) * 60 + Number(m[2]);
  }

  async function apiGet(path) {
    const resp = await fetch(path, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }

  async function apiPost(path, payload, _retried) {
    const resp = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRF-Token": siteState.csrfToken,
      },
      body: JSON.stringify(payload || {}),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.status === 403 && !_retried) {
      const fresh = await apiGet(`/api/public/showcase?home_city=${encodeURIComponent(siteState.homeCity)}`).catch(() => ({}));
      if (fresh.csrf_token) {
        siteState.csrfToken = fresh.csrf_token;
        return apiPost(path, payload, true);
      }
    }
    if (!resp.ok) throw new Error(data.error || `请求失败 (${resp.status})`);
    return data;
  }

  async function downloadParsedIcs(rawText) {
    const resp = await fetch("/api/public/parse-ics", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/calendar",
        "X-CSRF-Token": siteState.csrfToken,
      },
      body: JSON.stringify({ text: rawText, home_city: siteState.homeCity }),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.error || `导出失败 (${resp.status})`);
    }
    const icsText = await resp.text();
    const dataUrl = `data:text/calendar;charset=utf-8,${encodeURIComponent(icsText)}`;
    const link = el("a", { href: dataUrl, download: "liveecho-parsed-concert.ics" });
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  async function loadShowcaseData(forceRefresh) {
    const rf = forceRefresh ? "&refresh=1" : "";
    const data = await apiGet(`/api/public/showcase?home_city=${encodeURIComponent(siteState.homeCity)}${rf}`);
    siteState.csrfToken = data.csrf_token || siteState.csrfToken;
    siteState.authenticated = Boolean(data.authenticated);
    siteState.username = data.username || "";
    siteState.regions = data.regions || {};
    siteState.cityMapNodes = data.city_map_nodes || DEFAULT_CITY_MAP_NODES;
    siteState.venueGuides = data.venue_guides || [];
    siteState.presets = data.presets || [];
    siteState.culturePortals = data.culture_portals || [];
    siteState.concerts = data.concerts || [];
    siteState.festivalDemo = data.festival_demo || null;
    siteState.localOcrAvailable = Boolean(data.local_ocr_available);
    siteState.visionOcrAvailable = Boolean(data.vision_ocr_available);
    siteState.liveFetchedAt = data.live_fetched_at || "";
    siteState.liveSources = data.live_sources || [];
    siteState.lastShowcaseLoadMs = Date.now();
    if (siteState.concerts.length > 0 && !siteState.concerts.some((c) => c.id === siteState.expandedConcertId)) {
      siteState.expandedConcertId = siteState.concerts[0].id;
    }
    if (Array.isArray(data.followed_artists) && data.followed_artists.length > 0) {
      for (const nm of data.followed_artists) {
        if (nm) siteState.favoriteArtists.add(nm);
      }
    }

    if (!siteState.calMonthAutoPicked && siteState.concerts.length > 0) {
      const todayYmd = nowShanghai.toISOString().slice(0, 10);
      const allDates = [];
      for (const c of siteState.concerts) {
        const sd = (c.show_time || "").slice(0, 10);
        if (/^\d{4}-\d{2}-\d{2}$/.test(sd)) allDates.push(sd);
        for (const r of c.ticket_rounds || []) {
          const rd = (r.sale_time || "").slice(0, 10);
          if (/^\d{4}-\d{2}-\d{2}$/.test(rd)) allDates.push(rd);
        }
      }
      const upcoming = allDates.filter((d) => d >= todayYmd).sort();
      const chosen = upcoming[0] || allDates.sort()[0];
      if (chosen) {
        siteState.calYear = Number(chosen.slice(0, 4));
        siteState.calMonth = Number(chosen.slice(5, 7)) - 1;
        siteState.selectedCalDate = chosen;
        siteState.calMonthAutoPicked = true;
      }
    }

    const enterBtn = document.getElementById("btn-enter-app");
    if (enterBtn) {
      enterBtn.textContent = siteState.authenticated
        ? `工作台 (${siteState.username})`
        : "个人追踪库";
    }
    const dlAllBtn = document.getElementById("btn-download-all-ics");
    if (dlAllBtn) {
      dlAllBtn.setAttribute(
        "href",
        `/api/public/showcase-ics?id=all&home_city=${encodeURIComponent(siteState.homeCity)}`
      );
    }

    renderHeroKpiStrip();
    renderHeroSpotlight();
    renderWatchlistSection();
    renderDropsSection();
    renderDirectoryViewTabs();
    renderDirectoryCategoryTabs();
    renderDirectoryRegionTabs();
    renderDirectorySection();
    renderFestivalSection();
    renderApprovalsSection();
  }

  // ---------------- Canvas PNG Generators (Ticket Stub & Watchlist Poster) ----------------

  function wrapCanvasText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
    const chars = Array.from(String(text || ""));
    let line = "";
    let lineCount = 0;
    for (let i = 0; i < chars.length; i++) {
      const test = line + chars[i];
      if (ctx.measureText(test).width > maxWidth && line) {
        lineCount += 1;
        if (lineCount >= maxLines) {
          ctx.fillText(line.slice(0, -1) + "…", x, y);
          return y + lineHeight;
        }
        ctx.fillText(line, x, y);
        line = chars[i];
        y += lineHeight;
      } else {
        line = test;
      }
    }
    if (line) {
      ctx.fillText(line, x, y);
      y += lineHeight;
    }
    return y;
  }

  function renderStubCanvasDataUrl(stub) {
    const dark = siteState.theme === "dark";
    const canvas = document.createElement("canvas");
    canvas.width = 1200;
    canvas.height = 620;
    const ctx = canvas.getContext("2d");

    const bg = dark ? "#141210" : "#efe8da";
    const card = dark ? "#221e1a" : "#fffdf9";
    const ink = dark ? "#f5efe6" : "#171614";
    const muted = dark ? "#a89d8e" : "#6c655d";
    const accent = dark ? "#e64d36" : "#c83722";
    const brass = dark ? "#f0b254" : "#944808";
    const rule = dark ? "#473f36" : "#cfc5b3";

    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, 1200, 620);

    // Main ticket card
    ctx.fillStyle = card;
    ctx.strokeStyle = ink;
    ctx.lineWidth = 3;
    ctx.fillRect(42, 42, 1116, 536);
    ctx.strokeRect(42, 42, 1116, 536);

    // Left dark editorial header spine
    ctx.fillStyle = dark ? "#2f2923" : "#171614";
    ctx.fillRect(42, 42, 1116, 78);

    // Top band copy
    ctx.fillStyle = "#f5efe6";
    ctx.font = "700 20px ui-monospace, Menlo, monospace";
    ctx.fillText("LIVE ECHO · 现场回响 纪念票根 ARCHIVE PASS", 76, 89);
    ctx.fillStyle = accent;
    ctx.fillRect(910, 62, 214, 38);
    ctx.fillStyle = "#ffffff";
    ctx.font = "800 18px sans-serif";
    ctx.fillText("ADMIT ONE · 已核验", 932, 87);

    // Perforation tear line on the right stub
    ctx.save();
    ctx.setLineDash([8, 8]);
    ctx.strokeStyle = rule;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(860, 120);
    ctx.lineTo(860, 578);
    ctx.stroke();
    ctx.restore();

    // Semicircular ticket notches
    ctx.fillStyle = bg;
    ctx.beginPath();
    ctx.arc(860, 42, 20, 0, Math.PI * 2);
    ctx.arc(860, 578, 20, 0, Math.PI * 2);
    ctx.fill();

    // Main ticket body (left side)
    ctx.fillStyle = accent;
    ctx.font = "700 20px ui-monospace, Menlo, monospace";
    ctx.fillText(`${stub.city || "CHINA"} · ${stub.date || "2026"}`, 78, 174);

    ctx.fillStyle = ink;
    ctx.font = "800 46px 'Songti SC', 'Noto Serif SC', Georgia, sans-serif";
    wrapCanvasText(ctx, stub.artist || "现场演出", 78, 232, 740, 52, 1);

    ctx.fillStyle = muted;
    ctx.font = "600 22px sans-serif";
    wrapCanvasText(ctx, stub.title || stub.venue || "", 78, 274, 740, 30, 2);

    // Metadata strip
    ctx.fillStyle = dark ? "#1a1714" : "#f6f2e9";
    ctx.fillRect(78, 326, 742, 68);
    ctx.fillStyle = ink;
    ctx.font = "700 20px sans-serif";
    ctx.fillText(`座位：${stub.seat || "现场观演"}`, 98, 368);
    ctx.fillStyle = brass;
    ctx.font = "800 21px ui-monospace, Menlo, monospace";
    const stars = "★".repeat(Math.max(1, Math.min(5, Number(stub.rating || 5))));
    ctx.fillText(`¥${stub.paid || "--"}  ${stars}`, 620, 368);

    // Acoustics & Encore Memory
    ctx.fillStyle = muted;
    ctx.font = "700 16px sans-serif";
    ctx.fillText("声场与选座记录", 78, 430);
    ctx.fillStyle = ink;
    ctx.font = "500 18px sans-serif";
    wrapCanvasText(ctx, stub.acoustics || "现场音效通透，沉浸感极佳。", 78, 458, 742, 26, 2);

    ctx.fillStyle = muted;
    ctx.font = "700 16px sans-serif";
    ctx.fillText("安可瞬间", 78, 520);
    ctx.fillStyle = ink;
    ctx.font = "500 18px sans-serif";
    wrapCanvasText(ctx, stub.memory || "值得珍藏的一夜现场回响。", 78, 548, 742, 24, 1);

    // Right tear-off stub section
    ctx.fillStyle = accent;
    ctx.fillRect(900, 152, 66, 66);
    ctx.fillStyle = "#ffffff";
    ctx.font = "800 26px 'Songti SC', Georgia, serif";
    ctx.fillText("回响", 907, 194);

    ctx.fillStyle = ink;
    ctx.font = "800 22px sans-serif";
    ctx.fillText(stub.city || "中国现场", 982, 180);
    ctx.fillStyle = muted;
    ctx.font = "600 17px ui-monospace, Menlo, monospace";
    ctx.fillText(stub.date || "2026", 982, 208);

    ctx.fillStyle = muted;
    ctx.font = "700 15px sans-serif";
    ctx.fillText("STUB SERIAL", 900, 268);
    ctx.fillStyle = ink;
    ctx.font = "700 18px ui-monospace, Menlo, monospace";
    const serial = `LE-${String(stub.date || "2026").replace(/-/g, "")}-${String((stub.artist || "LIVE").length * 37).padStart(3, "0")}`;
    ctx.fillText(serial, 900, 294);

    ctx.fillStyle = muted;
    ctx.font = "700 15px sans-serif";
    ctx.fillText("PRICE PAID", 900, 344);
    ctx.fillStyle = accent;
    ctx.font = "800 32px ui-monospace, Menlo, monospace";
    ctx.fillText(`¥${stub.paid || "--"}`, 900, 384);

    // Decorative editorial barcode stripes
    ctx.fillStyle = ink;
    for (let i = 0; i < 38; i++) {
      const w = (i % 5 === 0 || i % 7 === 0) ? 4 : 2;
      if (i % 3 !== 2) {
        ctx.fillRect(900 + i * 6, 446, w, 74);
      }
    }
    ctx.fillStyle = muted;
    ctx.font = "600 13px ui-monospace, Menlo, monospace";
    ctx.fillText("LIVEECHO · COLLECTIBLE STUB", 900, 544);

    return canvas.toDataURL("image/png");
  }

  function renderWatchlistPosterDataUrl(favArray, alerts) {
    const dark = siteState.theme === "dark";
    const canvas = document.createElement("canvas");
    canvas.width = 1080;
    canvas.height = 1280;
    const ctx = canvas.getContext("2d");

    const bg = dark ? "#13110f" : "#f6f2e9";
    const card = dark ? "#221e1a" : "#fffdf9";
    const ink = dark ? "#f5efe6" : "#171614";
    const muted = dark ? "#a89d8e" : "#6c655d";
    const accent = dark ? "#e64d36" : "#c83722";
    const rule = dark ? "#473f36" : "#d3c9b7";

    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, 1080, 1280);

    // Header band
    ctx.fillStyle = dark ? "#2a241f" : "#171614";
    ctx.fillRect(48, 48, 984, 152);
    ctx.fillStyle = accent;
    ctx.fillRect(82, 82, 76, 76);
    ctx.fillStyle = "#ffffff";
    ctx.font = "800 30px 'Songti SC', Georgia, serif";
    ctx.fillText("回响", 90, 130);

    ctx.fillStyle = "#f5efe6";
    ctx.font = "800 34px 'Songti SC', Georgia, sans-serif";
    ctx.fillText("我的演唱会追星排期 & 预售雷达", 180, 118);
    ctx.fillStyle = "#c8bfb1";
    ctx.font = "600 19px ui-monospace, Menlo, monospace";
    ctx.fillText(`出发地：${siteState.homeCity} · 收藏 ${favArray.length} 组中外歌手 · LIVE ECHO`, 180, 154);

    // Favorited artists chip line
    ctx.fillStyle = accent;
    ctx.font = "700 18px ui-monospace, Menlo, monospace";
    ctx.fillText("WATCHLIST ARTISTS", 56, 248);
    ctx.fillStyle = ink;
    ctx.font = "700 24px sans-serif";
    wrapCanvasText(ctx, favArray.map((a) => `★ ${a}`).join("   "), 56, 286, 968, 36, 2);

    // Upcoming stops cards
    ctx.fillStyle = accent;
    ctx.font = "700 18px ui-monospace, Menlo, monospace";
    ctx.fillText("UPCOMING PRE-SALES & APPROVALS", 56, 386);

    const visibleAlerts = alerts.slice(0, 6);
    let y = 412;
    if (!visibleAlerts.length) {
      ctx.fillStyle = card;
      ctx.strokeStyle = rule;
      ctx.lineWidth = 2;
      ctx.fillRect(56, y, 968, 120);
      ctx.strokeRect(56, y, 968, 120);
      ctx.fillStyle = muted;
      ctx.font = "600 22px sans-serif";
      ctx.fillText("当前收藏艺人暂未定档新预售，持续关注大麦/猫眼/文旅过审动态。", 88, y + 68);
    } else {
      for (const al of visibleAlerts) {
        ctx.fillStyle = card;
        ctx.strokeStyle = rule;
        ctx.lineWidth = 2;
        ctx.fillRect(56, y, 968, 116);
        ctx.strokeRect(56, y, 968, 116);
        ctx.fillStyle = al.kind === "approval_early" ? "#166534" : accent;
        ctx.fillRect(56, y, 10, 116);

        ctx.fillStyle = ink;
        ctx.font = "800 25px sans-serif";
        ctx.fillText(`${al.artist} — ${al.city}站`, 88, y + 42);
        ctx.fillStyle = muted;
        ctx.font = "600 19px sans-serif";
        ctx.fillText(`${al.venue || "场馆待公布"} · 演出日 ${al.showTime}`, 88, y + 76);
        ctx.fillStyle = accent;
        ctx.font = "700 18px ui-monospace, Menlo, monospace";
        const rightMeta = al.presaleTime ? `开抢 ${al.presaleTime} (${al.platform})` : `${al.presaleLabel}`;
        ctx.fillText(rightMeta, 88, y + 104);
        y += 132;
      }
    }

    // Footer bar
    ctx.strokeStyle = rule;
    ctx.beginPath();
    ctx.moveTo(56, 1212);
    ctx.lineTo(1024, 1212);
    ctx.stroke();
    ctx.fillStyle = muted;
    ctx.font = "600 17px ui-monospace, Menlo, monospace";
    ctx.fillText("GENERATED BY LIVEECHO (现场回响) · 预售 / 回流 / 高铁 12306 一站追踪", 56, 1244);

    return canvas.toDataURL("image/png");
  }

  function openPngPreviewModal(title, dataUrl, filename) {
    openSiteModal(
      title,
      [
        el("img", { src: dataUrl, alt: title, className: "modal-preview-img" }),
        el("p", { className: "muted-line", text: "纯前端高清 Canvas 渲染，可直接保存 PNG 分享到微信/群聊/社交媒体。" }),
      ],
      [
        el("button", { type: "button", className: "site-btn site-btn-sm", onClick: closeSiteModal }, "关闭"),
        el("a", { href: dataUrl, download: filename, className: "site-btn site-btn-primary site-btn-sm" }, "⬇ 下载高清 PNG 图片"),
      ]
    );
  }

  function buildCurrentShareUrl() {
    const base = String(window.location.href || "").split("#")[0].split("?")[0];
    const params = new URLSearchParams();
    const favs = Array.from(siteState.favoriteArtists);
    if (favs.length) params.set("fav", favs.join(","));
    params.set("home", siteState.homeCity);
    if (siteState.theme === "dark") params.set("theme", "dark");
    return `${base}?${params.toString()}`;
  }

  function openShareWatchlistModal() {
    syncStateToUrl();
    const shareUrl = buildCurrentShareUrl();
    const copyAttempt = () => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard
          .writeText(shareUrl)
          .then(() => showSiteToast("已复制收藏清单分享链接！朋友打开即同步你的收藏歌手与出发地"))
          .catch(() => showShareFallback(shareUrl));
      } else {
        showShareFallback(shareUrl);
      }
    };
    copyAttempt();
  }

  function showShareFallback(shareUrl) {
    const inp = el("input", { type: "text", className: "share-link-box", value: shareUrl, readonly: true });
    openSiteModal(
      "分享我的收藏歌手与预售提醒清单",
      [
        el("p", { className: "muted-line", text: "复制下方链接发送给同行好友，打开后会自动载入你收藏的歌手列表、出发城市与主题设置：" }),
        inp,
      ],
      [
        el(
          "button",
          {
            type: "button",
            className: "site-btn site-btn-primary site-btn-sm",
            onClick: () => {
              inp.select();
              try {
                document.execCommand("copy");
                showSiteToast("已选中并复制分享链接！");
              } catch (_e) {
                showSiteToast("请按 Ctrl+C / Cmd+C 复制上方链接");
              }
            },
          },
          "全选链接"
        ),
        el("button", { type: "button", className: "site-btn site-btn-sm", onClick: closeSiteModal }, "关闭"),
      ]
    );
    window.setTimeout(() => inp.select(), 60);
  }

  // ---------------- Artist Bookmarking & Upcoming Pre-Sale Alert Engine ----------------

  function isArtistFavorited(artistName) {
    const clean = (artistName || "").trim();
    if (!clean) return false;
    if (siteState.favoriteArtists.has(clean)) return true;
    const lower = clean.toLowerCase();
    for (const fav of siteState.favoriteArtists) {
      if (fav.toLowerCase() === lower) return true;
    }
    return false;
  }

  function concertMatchesArtist(concert, artistName) {
    const target = (artistName || "").trim().toLowerCase();
    if (!target) return false;
    const preset = (siteState.presets || []).find(
      (p) =>
        p.name.toLowerCase() === target ||
        (p.aliases || []).some((a) => String(a).toLowerCase() === target)
    );
    const tokens = preset
      ? [preset.name.toLowerCase()].concat((preset.aliases || []).map((a) => String(a).toLowerCase()))
      : [target];
    const lineupText = Array.isArray(concert.lineup_artists) ? concert.lineup_artists.join(" ") : "";
    const hay = `${concert.artist_name || ""} ${lineupText} ${concert.title || ""}`.toLowerCase();
    return tokens.some((tk) => tk && hay.includes(tk));
  }

  function collectPresalesForArtists(artistList) {
    const alerts = [];
    for (const artistName of artistList) {
      for (const c of siteState.concerts) {
        if (!concertMatchesArtist(c, artistName)) continue;
        const rounds = c.ticket_rounds || [];
        const refunds = (c.refund_tiers || []).filter((rf) => rf.expect_return_drop);
        if (rounds.length > 0) {
          for (const r of rounds) {
            alerts.push({
              key: `fav-drop-${c.id}-${r.id || r.sale_time}`,
              artist: artistName,
              concert: c,
              city: c.city,
              venue: c.venue,
              showTime: c.show_time,
              presaleLabel: r.round_label || "门票预售",
              presaleTime: r.sale_time,
              ms: parseShanghaiMs(r.sale_time),
              platform: r.platform || c.platform,
              price: c.price_text,
              url: r.booking_url || c.ticket_url,
              kind: "presale",
            });
          }
        } else if (refunds.length > 0) {
          const rf0 = refunds[0];
          alerts.push({
            key: `fav-sniper-${c.id}-${rf0.id || rf0.cutoff_time}`,
            artist: artistName,
            concert: c,
            city: c.city,
            venue: c.venue,
            showTime: c.show_time,
            presaleLabel: rf0.tier_label || "退票回流窗口",
            presaleTime: rf0.cutoff_time,
            ms: parseShanghaiMs(rf0.cutoff_time),
            platform: c.platform,
            price: c.price_text,
            url: c.ticket_url,
            kind: "return_drop",
          });
        } else if (c.status === "approved_pending") {
          alerts.push({
            key: `fav-app-${c.id}`,
            artist: artistName,
            concert: c,
            city: c.city,
            venue: c.venue,
            showTime: c.show_time,
            presaleLabel: `文旅已过审（${c.approval_doc_no || "即将官宣预售"}）`,
            presaleTime: "",
            ms: null,
            platform: c.approval_source || "省市文旅局",
            price: c.price_text,
            url: c.ticket_url,
            kind: "approval_early",
          });
        }
      }
    }
    const seen = new Set();
    const deduped = alerts.filter((a) => {
      if (seen.has(a.key)) return false;
      seen.add(a.key);
      return true;
    });
    deduped.sort((a, b) => {
      if (a.ms && b.ms) return a.ms - b.ms;
      if (a.ms) return -1;
      if (b.ms) return 1;
      return String(a.showTime).localeCompare(String(b.showTime));
    });
    return deduped;
  }

  function mergeConcertsIntoPage(newItems, fallbackArtist) {
    const existingKeys = new Set(siteState.concerts.map((c) => `${c.city}|${(c.show_time || "").slice(0, 10)}|${c.title}`));
    let added = 0;
    for (const dc of newItems || []) {
      const dk = `${dc.city}|${(dc.show_time || "").slice(0, 10)}|${dc.title}`;
      if (!existingKeys.has(dk)) {
        existingKeys.add(dk);
        added += 1;
        siteState.concerts.push({
          id: dc.id || Math.floor(2000 + Math.random() * 7000),
          artist_name: dc.artist_name || fallbackArtist || "现场艺人",
          artist_category: dc.artist_category || "cn",
          title: dc.title || `${dc.artist_name || fallbackArtist || "演出"} 专场`,
          city: dc.city || "待定",
          region: dc.region || "other",
          venue: dc.venue || "",
          show_time: dc.show_time || "",
          price_text: dc.price_text || "",
          platform: dc.platform || "大麦",
          ticket_url: dc.ticket_url || "",
          status: dc.status || "upcoming_drop",
          approval_doc_no: dc.approval_doc_no || "",
          approval_source: dc.approval_source || "",
          event_kind: dc.event_kind || "concert",
          ticket_rounds: dc.ticket_rounds || [],
          refund_tiers: dc.refund_tiers || [],
          rail_plan: dc.rail_plan || { is_cross_city: false },
          trip_estimate: dc.trip_estimate || null,
          venue_guide: dc.venue_guide || null,
        });
      }
    }
    return added;
  }

  async function toggleFavoriteArtist(profOrName, discoveredConcerts) {
    const prof =
      typeof profOrName === "string"
        ? { name: profOrName.trim(), aliases: [], genre: "", region_origin: "" }
        : profOrName || {};
    const name = (prof.name || "").trim();
    if (!name) return;

    if (Array.isArray(discoveredConcerts) && discoveredConcerts.length > 0) {
      mergeConcertsIntoPage(discoveredConcerts, name);
    }

    let existingMatch = "";
    for (const f of siteState.favoriteArtists) {
      if (f.toLowerCase() === name.toLowerCase()) {
        existingMatch = f;
        break;
      }
    }

    if (existingMatch) {
      siteState.favoriteArtists.delete(existingMatch);
      syncStateToUrl();
      showSiteToast(`已取消收藏「${existingMatch}」`);
    } else {
      siteState.favoriteArtists.add(name);
      syncStateToUrl();
      const hits = collectPresalesForArtists([name]);
      const cities = Array.from(new Set(hits.map((h) => h.city).filter(Boolean)));
      if (cities.length > 0) {
        showSiteToast(`★ 已收藏「${name}」！即将预售/过审城市：${cities.join("、")}`);
      } else {
        showSiteToast(`★ 已收藏「${name}」！已加入「我收藏的歌手」预售雷达`);
      }
      if (siteState.authenticated) {
        apiPost("/api/artists/upsert", {
          name,
          aliases: prof.aliases || [],
          genre: prof.genre || "",
          region_origin: prof.region_origin || "",
          auto_discover: true,
          scan_immediately: false,
        }).catch(() => {});
      }
    }

    renderHeroKpiStrip();
    renderWatchlistSection();
    renderDirectorySection();
    renderFestivalSection();
    if (siteState.lastSearchedBundle) {
      renderSearchResultBundle(siteState.lastSearchedBundle);
    }
  }

  function enableBrowserPresaleAlerts() {
    if (!("Notification" in window)) {
      siteState.browserAlertsEnabled = true;
      renderWatchlistSection();
      showSiteToast(`当前环境不支持系统弹窗，已开启页内提前 ${siteState.alertLeadMinutes} 分钟预售强提醒！`);
      return;
    }
    try {
      Notification.requestPermission().then((perm) => {
        siteState.browserAlertsEnabled = true;
        renderWatchlistSection();
        if (perm === "granted") {
          showSiteToast(`已开启浏览器桌面预售提醒！将在开票前 ${siteState.alertLeadMinutes} 分钟及 5 分钟弹窗提醒。`);
        } else {
          showSiteToast("已开启页内预售强提醒（如需系统弹窗请在浏览器地址栏允许通知）。");
        }
      });
    } catch (_e) {
      siteState.browserAlertsEnabled = true;
      renderWatchlistSection();
      showSiteToast("已开启页内预售开票提醒！");
    }
  }

  function renderWatchlistSection() {
    const count = siteState.favoriteArtists.size;
    const navLink = document.getElementById("nav-watchlist");
    if (navLink) navLink.textContent = `收藏提醒 (${count})`;
    const dockBtn = document.getElementById("dock-watchlist-btn");
    if (dockBtn) dockBtn.textContent = `★ 收藏提醒 (${count})`;

    const actionsHost = document.getElementById("watchlist-header-actions");
    const chipsHost = document.getElementById("watchlist-chips-bar");
    const gridHost = document.getElementById("watchlist-presale-grid");
    if (!chipsHost || !gridHost) return;

    const favArray = Array.from(siteState.favoriteArtists);
    const presaleAlerts = collectPresalesForArtists(favArray);

    // Group multi-round alerts by concert stop so Coldplay/Eason don't render duplicate cards
    const groupedMap = new Map();
    for (const al of presaleAlerts) {
      const gid = al.concert && al.concert.id ? `c-${al.concert.id}` : `${al.artist}|${al.city}|${al.showTime}`;
      if (!groupedMap.has(gid)) {
        groupedMap.set(gid, {
          primary: al,
          rounds: [al],
        });
      } else {
        groupedMap.get(gid).rounds.push(al);
      }
    }
    const groupedStops = Array.from(groupedMap.values());

    if (actionsHost) {
      const icsHref = `/api/public/showcase-ics?artists=${encodeURIComponent(favArray.join(","))}&home_city=${encodeURIComponent(siteState.homeCity)}`;
      const leadSelect = el(
        "select",
        {
          "aria-label": "自定义提前提醒分钟数",
          onChange: (ev) => {
            siteState.alertLeadMinutes = Number(ev.target.value) || 15;
            showSiteToast(`已调整预售提前提醒为开票前 ${siteState.alertLeadMinutes} 分钟`);
          },
        },
        [15, 30, 60].map((m) =>
          el("option", { value: String(m), selected: siteState.alertLeadMinutes === m, text: `提前 ${m} 分钟` })
        )
      );

      setChildren(
        actionsHost,
        el("label", { className: "lead-select-wrap" }, el("span", { className: "muted-line", text: "提醒时机" }), leadSelect),
        el(
          "button",
          {
            type: "button",
            className: siteState.browserAlertsEnabled ? "site-btn site-btn-sm site-btn-primary" : "site-btn site-btn-sm",
            onClick: enableBrowserPresaleAlerts,
          },
          siteState.browserAlertsEnabled ? "◎ 浏览器提醒已开" : "◎ 开启浏览器提醒"
        ),
        favArray.length > 0
          ? el("a", { href: icsHref, className: "site-btn site-btn-sm" }, "↓ 导出收藏 .ics")
          : null,
        favArray.length > 0
          ? el(
              "button",
              {
                type: "button",
                className: "site-btn site-btn-sm",
                onClick: () => {
                  const dataUrl = renderWatchlistPosterDataUrl(favArray, presaleAlerts);
                  openPngPreviewModal("我的追星排期海报高清预览 (PNG)", dataUrl, "liveecho-my-watchlist-poster.png");
                },
              },
              "↓ 导出排期海报 PNG"
            )
          : null,
        favArray.length > 0
          ? el("button", { type: "button", className: "site-btn site-btn-sm", onClick: openShareWatchlistModal }, "↗ 分享收藏链接")
          : null,
        favArray.length > 0
          ? el(
              "button",
              {
                type: "button",
                className: siteState.onlyFavorites ? "site-btn site-btn-sm site-btn-primary" : "site-btn site-btn-sm",
                onClick: () => {
                  siteState.onlyFavorites = !siteState.onlyFavorites;
                  renderWatchlistSection();
                  renderDirectorySection();
                  const dirSec = document.getElementById("directory");
                  if (siteState.onlyFavorites && dirSec) dirSec.scrollIntoView({ behavior: "smooth" });
                },
              },
              siteState.onlyFavorites ? "✓ 排期仅看收藏中" : "排期只看收藏"
            )
          : null
      );
    }

    if (!favArray.length) {
      setChildren(chipsHost, el("span", { className: "muted-line", text: "暂未收藏歌手 — 在顶部搜索框输入任意中外艺人并点击「☆ 收藏」即可开启监控。" }));
      setChildren(
        gridHost,
        el(
          "div",
          { className: "watchlist-empty-box" },
          el("strong", { text: "还没有收藏的歌手或乐队" }),
          el("p", {
            className: "muted-line mt-xs",
            text: "试试在顶部搜索「Coldplay」「Linkin Park」「Bruno Mars」「Dua Lipa」「YOASOBI」「Fujii Kaze」「陈奕迅」或「万能青年旅店」，一键收藏即可自动追踪他们在全国及港澳各城市的即将预售动态。",
          })
        )
      );
      return;
    }

    setChildren(
      chipsHost,
      el("span", { className: "muted-line", text: `已收藏 ${favArray.length} 组：` }),
      favArray.map((nm) => {
        const artistHits = collectPresalesForArtists([nm]);
        const cityList = Array.from(new Set(artistHits.map((h) => h.city).filter(Boolean)));
        return el(
          "span",
          { className: cityList.length ? "fav-artist-chip is-highlighted" : "fav-artist-chip" },
          el(
            "button",
            {
              type: "button",
              className: "fav-chip-name-btn",
              onClick: () => {
                const inp = document.getElementById("hero-artist-input");
                if (inp) inp.value = nm;
                runHeroArtistSearch(nm);
              },
            },
            cityList.length ? `★ ${nm}（${cityList.join("/")}）` : `★ ${nm}`
          ),
          el(
            "button",
            {
              type: "button",
              className: "fav-chip-remove-btn",
              title: `取消收藏 ${nm}`,
              "aria-label": `取消收藏 ${nm}`,
              onClick: () => toggleFavoriteArtist(nm),
            },
            "×"
          )
        );
      })
    );

    const artistsWithoutStops = favArray.filter((nm) => collectPresalesForArtists([nm]).length === 0);

    setChildren(
      gridHost,
      groupedStops.map(({ primary: al, rounds }) => {
        const badgeClass =
          al.kind === "approval_early"
            ? "badge-inline badge-approval"
            : al.kind === "return_drop"
              ? "badge-inline badge-sniper"
              : "badge-inline badge-drop";
        const badgeText =
          al.kind === "approval_early"
            ? `${al.city}站 · 文旅过审待宣`
            : al.kind === "return_drop"
              ? `${al.city}站 · 退票回流窗口`
              : `${al.city}站 · ${al.presaleLabel}`;
        const trip = al.concert && al.concert.trip_estimate;

        return el(
          "article",
          { className: al.kind === "approval_early" ? "watchlist-alert-card is-approval" : "watchlist-alert-card" },
          el(
            "div",
            { className: "flex-row-between" },
            el("span", { className: badgeClass, text: badgeText }),
            al.ms
              ? el("span", {
                  className: "countdown-big",
                  "data-site-countdown": String(al.ms),
                  text: formatCountdown(al.ms, Date.now()),
                })
              : el("span", { className: "muted-line", text: "待定档开票日" })
          ),
          el(
            "div",
            null,
            el("strong", { text: `${al.artist} — ${al.city} · ${al.venue || "场馆待公布"}` }),
            rounds.length > 1
              ? el(
                  "div",
                  { className: "watchlist-rounds-list mt-xs" },
                  rounds.map((r) =>
                    el(
                      "div",
                      { className: "watchlist-round-line" },
                      el("span", { text: `• ${r.presaleLabel}（${r.platform}）` }),
                      el("span", { className: "tour-date-col", text: r.presaleTime || "待定" })
                    )
                  )
                )
              : el("div", {
                  className: "muted-line mt-xs",
                  text: al.presaleTime
                    ? `预售开抢：${al.presaleTime}（${al.platform}） · 票价 ${al.price || "待公布"}`
                    : `${al.presaleLabel} · 演出日 ${al.showTime} · ${al.platform}`,
                }),
            trip && trip.is_cross_city
              ? el("div", {
                  className: "muted-line mt-xs",
                  text: `${siteState.homeCity}出发高铁单程约 ${trip.hsr_hours_one_way}h · 来源：${al.concert?.data_source || al.platform}`,
                })
              : el("div", {
                  className: "muted-line mt-xs",
                  text: `来源：${al.concert?.data_source || al.platform}`,
                })
          ),
          el(
            "div",
            { className: "flex-row-between" },
            el("span", { className: "muted-line", text: `演出日：${al.showTime}` }),
            el(
              "div",
              { className: "flex-row-wrap" },
              al.concert && al.concert.id
                ? el(
                    "a",
                    {
                      href: `/api/public/showcase-ics?id=${encodeURIComponent(al.concert.id)}&home_city=${encodeURIComponent(siteState.homeCity)}`,
                      className: "tag-pill",
                    },
                    "闹钟 .ics"
                  )
                : null,
              al.url
                ? el("a", { href: al.url, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "直达预售页 ↗")
                : null
            )
          )
        );
      }),
      artistsWithoutStops.map((nm) => {
        const enc = encodeURIComponent(nm);
        return el(
          "article",
          { className: "watchlist-alert-card" },
          el(
            "div",
            { className: "flex-row-between" },
            el("span", { className: "badge-inline badge-approval", text: "★ 已收藏监控中" }),
            el("span", { className: "muted-line", text: "暂未检出定档预售" })
          ),
          el(
            "div",
            null,
            el("strong", { text: `${nm} — 中外巡演监控已开启` }),
            el("div", {
              className: "muted-line mt-xs",
              text: "在下方解析台粘贴该艺人任意官宣并加入排期，系统将立即在此处高亮提示预售城市。",
            })
          ),
          el(
            "div",
            { className: "flex-row-wrap" },
            el("a", { href: `https://search.damai.cn/search.htm?keyword=${enc}`, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "查大麦 ↗"),
            el("a", { href: `https://www.showstart.com/event/list?keyword=${enc}`, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "查秀动 ↗"),
            el("a", { href: `https://www.songkick.com/search?query=${enc}&type=artists`, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "Songkick ↗")
          )
        );
      })
    );
  }

  // ---------------- Section 1: Hero KPI, Quick Search & Spotlight ----------------

  function renderHeroKpiStrip() {
    const strip = document.getElementById("hero-kpi-strip");
    if (!strip) return;
    const total = siteState.concerts.length;
    const intlCount = siteState.concerts.filter((c) => c.artist_category === "intl_west" || c.artist_category === "intl_jpkr").length;
    let dropWindows = 0;
    for (const c of siteState.concerts) {
      dropWindows += (c.ticket_rounds || []).length;
      dropWindows += (c.refund_tiers || []).filter((rf) => rf.expect_return_drop).length;
    }
    const items = [
      {
        num: `${total} 场`,
        label: "秀动实时在售中国演出",
        accent: false,
        onClick: () => {
          siteState.selectedCategory = "all";
          siteState.onlyFavorites = false;
          renderDirectoryCategoryTabs();
          renderDirectorySection();
          const sec = document.getElementById("directory");
          if (sec) sec.scrollIntoView({ behavior: "smooth" });
        },
      },
      {
        num: `${intlCount} 场`,
        label: "当前检出海外艺人来华",
        accent: false,
        onClick: () => {
          siteState.selectedCategory = "intl_west";
          siteState.onlyFavorites = false;
          renderDirectoryCategoryTabs();
          renderDirectorySection();
          const sec = document.getElementById("directory");
          if (sec) sec.scrollIntoView({ behavior: "smooth" });
        },
      },
      {
        num: siteState.liveFetchedAt ? siteState.liveFetchedAt.slice(11, 16) : "实时",
        label: "秀动 + Songkick 同步",
        accent: true,
        onClick: () => {
          const sec = document.getElementById("drops");
          if (sec) sec.scrollIntoView({ behavior: "smooth" });
        },
      },
      {
        num: `${siteState.favoriteArtists.size} 组`,
        label: "我的收藏关注歌手",
        accent: true,
        onClick: () => {
          const sec = document.getElementById("watchlist");
          if (sec) sec.scrollIntoView({ behavior: "smooth" });
        },
      },
    ];
    setChildren(
      strip,
      items.map((it) =>
        el(
          "button",
          { type: "button", className: "hero-kpi-item", onClick: it.onClick },
          el("span", { className: it.accent ? "hero-kpi-num is-accent" : "hero-kpi-num", text: it.num }),
          el("span", { className: "hero-kpi-label", text: it.label })
        )
      )
    );
  }

  function renderHeroQuickArtists() {
    const row = document.getElementById("hero-quick-artists");
    if (!row) return;
    const hotItems = [
      { query: "Coldplay", label: "Coldplay" },
      { query: "Linkin Park", label: "Linkin Park" },
      { query: "Bruno Mars", label: "Bruno Mars" },
      { query: "Dua Lipa", label: "Dua Lipa" },
      { query: "YOASOBI", label: "YOASOBI" },
      { query: "ONE OK ROCK", label: "ONE OK ROCK" },
      { query: "Fujii Kaze", label: "Fujii Kaze" },
      { query: "SEVENTEEN", label: "SEVENTEEN" },
      { query: "BLACKPINK", label: "BLACKPINK" },
      { query: "陈奕迅", label: "陈奕迅" },
      { query: "万能青年旅店", label: "万能青年旅店" },
    ];
    setChildren(
      row,
      el("span", { text: "热门快搜：" }),
      hotItems.map((it) =>
        el(
          "button",
          {
            type: "button",
            className: isArtistFavorited(it.query) ? "tag-pill active" : "tag-pill",
            onClick: () => {
              const inp = document.getElementById("hero-artist-input");
              if (inp) inp.value = it.query;
              runHeroArtistSearch(it.query);
            },
          },
          isArtistFavorited(it.query) ? `★ ${it.label}` : it.label
        )
      )
    );
  }

  function renderSearchResultBundle(bundle) {
    const drawer = document.getElementById("hero-search-result-panel");
    if (!drawer || !bundle) return;
    drawer.hidden = false;

    const prof = bundle.primary_profile || { name: "", genre: "", aliases: [] };
    const presales = bundle.upcoming_presales || [];
    const globalConcerts = bundle.global_concerts || [];
    const cities = bundle.upcoming_cities || Array.from(new Set(presales.map((p) => p.city).filter(Boolean)));
    const links = bundle.search_links || {};
    const favorited = isArtistFavorited(prof.name);
    const checkedLabel = Array.isArray(bundle.live_sources_checked) && bundle.live_sources_checked.length
      ? `实时核验源：${bundle.live_sources_checked.join(" + ")}${bundle.fetched_at ? `（${bundle.fetched_at}）` : ""}`
      : "实时核验源：ShowStart 秀动 + Songkick 全球排期";

    setChildren(
      drawer,
      el(
        "div",
        { className: "flex-row-between" },
        el(
          "div",
          null,
          el("strong", { text: prof.name }),
          el("div", {
            className: "muted-line",
            text: [
              prof.genre,
              prof.region_origin,
              checkedLabel,
            ]
              .filter(Boolean)
              .join(" · "),
          })
        ),
        el(
          "div",
          { className: "flex-row-wrap" },
          el(
            "button",
            {
              type: "button",
              id: "btn-toggle-search-fav",
              className: favorited ? "btn-fav-star is-favorited" : "btn-fav-star",
              onClick: () => {
                toggleFavoriteArtist(prof, bundle.concerts || []);
                renderHeroQuickArtists();
              },
            },
            favorited ? `★ 已收藏「${prof.name}」` : `☆ 收藏「${prof.name}」`
          )
        )
      ),
      presales.length > 0
        ? el(
            "div",
            { className: "presale-summary-banner" },
            el("strong", {
              text: `已检出「${prof.name}」在中国内地 / 港澳的实时演出（共 ${cities.length} 个城市）：`,
            }),
            el(
              "div",
              { className: "presale-cities-strip" },
              cities.map((ct) => el("span", { className: "city-presale-pill", text: `${ct}站` }))
            ),
            el(
              "div",
              { className: "mt-sm" },
              presales.slice(0, 6).map((ps) => {
                const saleMs = ps.presale_time ? parseShanghaiMs(ps.presale_time) : null;
                return el(
                  "div",
                  { className: "slot-line" },
                  el(
                    "span",
                    null,
                    el("strong", { text: `[${ps.city}站] ` }),
                    `${ps.title || ps.presale_label} · `,
                    ps.presale_time ? `开售 ${ps.presale_time}` : `演出 ${ps.show_time}`,
                    ` · ${ps.venue || "场馆见原页"} · 来源：${ps.data_source || ps.platform}`
                  ),
                  el(
                    "span",
                    { className: "flex-row-wrap" },
                    saleMs
                      ? el("span", {
                          className: "badge-inline badge-drop",
                          "data-site-countdown": String(saleMs),
                          text: formatCountdown(saleMs, Date.now()),
                        })
                      : el("span", { className: "badge-inline badge-approval", text: ps.data_source || "实时核验" }),
                    ps.ticket_url
                      ? el("a", { href: ps.ticket_url, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "官方原页核验 ↗")
                      : null
                  )
                );
              })
            )
          )
        : el(
            "div",
            { className: "venue-guide-tip mt-sm" },
            el("strong", { text: `暂未检出「${prof.name}」在中国内地或港澳的已确认官方演出。` }),
            el("div", {
              className: "muted-line mt-xs",
              text: "系统已实时核验 ShowStart 与 Songkick，不虚构未官宣场次。若你在大麦/微博/Live Nation 看到新官宣，可直接点击下方官方入口核查，或粘贴通告到下方解析台录入。",
            })
          ),
      globalConcerts.length > 0
        ? el(
            "div",
            { className: "rail-callout mt-sm" },
            el("strong", { text: `全球其他国家/地区已确认巡演（来源：Songkick 实时抓取 · 非中国内地/港澳站）：` }),
            globalConcerts.slice(0, 5).map((gc) =>
              el(
                "div",
                { className: "slot-line" },
                el(
                  "span",
                  null,
                  el("strong", { text: `${(gc.show_time || "").slice(0, 10)} · ${gc.city}${gc.country ? `, ${gc.country}` : ""}` }),
                  ` — ${gc.venue || gc.title}`
                ),
                gc.ticket_url
                  ? el("a", { href: gc.ticket_url, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "Songkick 原页 ↗")
                  : null
              )
            )
          )
        : null,
      el(
        "div",
        { className: "flex-row-wrap mt-sm" },
        links.damai ? el("a", { href: links.damai, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "大麦核查 ↗") : null,
        links.maoyan ? el("a", { href: links.maoyan, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "猫眼核查 ↗") : null,
        links.showstart ? el("a", { href: links.showstart, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "秀动核查 ↗") : null,
        links.livenation ? el("a", { href: links.livenation, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "Live Nation 中国 ↗") : null,
        links.songkick ? el("a", { href: links.songkick, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "Songkick 全球排期 ↗") : null,
        links.weibo ? el("a", { href: links.weibo, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "微博官宣 ↗") : null
      )
    );
  }

  async function runHeroArtistSearch(query) {
    const q = (query || "").trim();
    if (!q) return;
    const drawer = document.getElementById("hero-search-result-panel");
    const btn = document.getElementById("hero-artist-submit");
    if (!drawer) return;
    drawer.hidden = false;
    drawer.replaceChildren(el("p", { className: "muted-line", text: `正在实时检索「${q}」的中外音乐人档案与近期预售城市...` }));
    if (btn) btn.disabled = true;

    try {
      const bundle = await apiGet(`/api/public/artist-preview?q=${encodeURIComponent(q)}`);
      if (!bundle.primary_profile) {
        bundle.primary_profile = { name: q, genre: "", aliases: [] };
      }
      siteState.lastSearchedBundle = bundle;
      renderSearchResultBundle(bundle);
    } catch (err) {
      drawer.replaceChildren(el("p", { className: "muted-line", text: `检索提示：${err.message}` }));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function renderHeroSpotlight() {
    const box = document.getElementById("hero-spotlight-card");
    if (!box) return;
    if (!siteState.concerts.length) {
      box.replaceChildren(
        el("div", { className: "poster-top-band" }, el("span", { text: "LIVE FEED · 实时演出同步" }), el("span", { text: "ShowStart + Songkick" })),
        el(
          "div",
          { className: "poster-body" },
          el("h2", { className: "poster-artist", text: "实时数据连接中" }),
          el("p", { className: "poster-subtitle", text: "暂未拉取到实时在售演出，可在左侧搜索任意中外艺人实时核验 ShowStart / Songkick，或粘贴官方通告到下方解析台。" })
        )
      );
      return;
    }

    // Curate top 3 real live concerts (prioritize upcoming drops, real overseas acts touring China, and nearest live shows)
    const intlLive = siteState.concerts.find((c) => c.artist_category === "intl_west" || c.artist_category === "intl_jpkr");
    const firstCn = siteState.concerts.find((c) => c !== intlLive);
    const secondCn = siteState.concerts.find((c) => c !== intlLive && c !== firstCn);
    const spotlightPool = [intlLive, firstCn, secondCn].filter(Boolean);
    const idx = ((siteState.spotlightIndex % spotlightPool.length) + spotlightPool.length) % spotlightPool.length;
    const feat = spotlightPool[idx];

    const round = (feat.ticket_rounds && feat.ticket_rounds[0]) || null;
    const saleMs = round ? parseShanghaiMs(round.sale_time) : parseShanghaiMs(feat.show_time);
    const refund0 = (feat.refund_tiers && feat.refund_tiers[0]) || null;
    const rail = feat.rail_plan || {};
    const trip = feat.trip_estimate || null;

    box.replaceChildren(
      el(
        "div",
        { className: "poster-top-band" },
        el("span", { text: `LIVE · ${feat.city} · ${feat.data_source || feat.platform}` }),
        el(
          "span",
          { className: "spotlight-pager" },
          el(
            "button",
            {
              type: "button",
              className: "spotlight-nav-btn",
              "aria-label": "上一焦点场次",
              onClick: () => {
                siteState.spotlightIndex = (idx - 1 + spotlightPool.length) % spotlightPool.length;
                renderHeroSpotlight();
              },
            },
            "‹"
          ),
          el("span", { text: `${idx + 1}/${spotlightPool.length}` }),
          el(
            "button",
            {
              type: "button",
              className: "spotlight-nav-btn",
              "aria-label": "下一焦点场次",
              onClick: () => {
                siteState.spotlightIndex = (idx + 1) % spotlightPool.length;
                renderHeroSpotlight();
              },
            },
            "›"
          )
        )
      ),
      el(
        "div",
        { className: "poster-body" },
        el("h2", { className: "poster-artist", text: feat.artist_name }),
        feat.title && feat.title !== feat.artist_name ? el("p", { className: "poster-subtitle", text: feat.title }) : null,
        el(
          "div",
          { className: "poster-Countdown-block" },
          el(
            "div",
            null,
            el("div", { className: "muted-line", text: round ? `${round.round_label}开启倒计时` : "距开演倒计时" }),
            el("strong", { text: round ? round.sale_time : feat.show_time })
          ),
          el("div", {
            className: "countdown-big",
            "data-site-countdown": String(saleMs || ""),
            text: saleMs ? formatCountdown(saleMs, Date.now()) : "--:--:--",
          })
        ),
        el(
          "div",
          { className: "poster-meta-list" },
          el("div", { text: `演出时间：${feat.show_time}` }),
          el("div", { text: `演出场馆：${feat.venue || "详见官方购票页"}` }),
          el("div", { text: `官方票价：${feat.price_text || "以官方页为准"}` }),
          el("div", { text: `数据来源：${feat.data_source || feat.platform}${siteState.liveFetchedAt ? `（同步于 ${siteState.liveFetchedAt}）` : ""}` }),
          refund0 ? el("div", { text: `首波回流窗口：${refund0.cutoff_time}（48h 免费退截止）` }) : null,
          rail.is_cross_city
            ? el("div", {
                text: `12306 高铁（${rail.home_city}出发）：${formatRailSaleStatus(rail.outbound_12306_sale_time)}${trip ? ` · 单程约 ${trip.hsr_hours_one_way}h` : ""}`,
              })
            : el("div", { text: `同城观演（出发地：${siteState.homeCity}，顶部可切换城市查跨城高铁）` })
        )
      ),
      el(
        "div",
        { className: "poster-perforated-foot" },
        el(
          "a",
          {
            href: `/api/public/showcase-ics?id=${encodeURIComponent(feat.id)}&home_city=${encodeURIComponent(siteState.homeCity)}`,
            className: "site-btn site-btn-sm",
          },
          "↓ 下载本场日历 (.ics)"
        ),
        feat.ticket_url
          ? el(
              "a",
              {
                href: feat.ticket_url,
                target: "_blank",
                rel: "noopener noreferrer",
                className: "site-btn site-btn-sm site-btn-primary",
              },
              "前往官方购票页 ↗"
            )
          : null
      )
    );
  }

  // ---------------- Section 2: Drops & Returned-Ticket Snipers ----------------

  function renderDropsSection() {
    const container = document.getElementById("drops-schedule-list");
    if (!container) return;

    const entries = [];
    for (const c of siteState.concerts) {
      for (const r of c.ticket_rounds || []) {
        const ms = parseShanghaiMs(r.sale_time);
        if (ms) {
          entries.push({
            key: `drop-${c.id}-${r.id || r.sale_time}`,
            kind: "drop",
            concert: c,
            badge: `抢票 · ${r.round_label}`,
            when: r.sale_time,
            platform: r.platform || c.platform,
            url: r.booking_url || c.ticket_url,
            ms,
          });
        }
      }
      for (const rf of c.refund_tiers || []) {
        if (!rf.expect_return_drop) continue;
        const ms = parseShanghaiMs(rf.cutoff_time);
        if (ms) {
          entries.push({
            key: `sniper-${c.id}-${rf.id || rf.cutoff_time}`,
            kind: "sniper",
            concert: c,
            badge: "回流票狙击",
            when: rf.cutoff_time,
            platform: `${c.platform} · ${rf.tier_label}`,
            url: c.ticket_url,
            ms,
          });
        }
      }
    }
    entries.sort((a, b) => a.ms - b.ms);

    // Fill remaining slots with real live upcoming ShowStart concerts when no custom ticket rounds are logged yet
    if (entries.length < 6) {
      for (const c of siteState.concerts) {
        if (entries.length >= 6) break;
        const ms = parseShanghaiMs(c.show_time);
        if (!ms) continue;
        entries.push({
          key: `live-${c.id}`,
          kind: "live_show",
          concert: c,
          badge: "秀动实时在售",
          when: c.show_time,
          platform: `${c.platform} · ${c.price_text || "见原页"}`,
          url: c.ticket_url,
          ms,
        });
      }
    }

    setChildren(
      container,
      entries.slice(0, 6).map((ent) => {
        const makeCheck = (ckId, label) => {
          const stateKey = `${ent.key}:${ckId}`;
          const cb = el("input", {
            type: "checkbox",
            checked: Boolean(siteState.prepChecks[stateKey]),
            onChange: () => {
              siteState.prepChecks[stateKey] = cb.checked;
              if (cb.checked) showSiteToast(`已勾选「${label}」准备就绪`);
            },
          });
          return el("label", null, cb, label);
        };

        const countdownPrefix = ent.kind === "sniper" ? "距回流" : ent.kind === "live_show" ? "距开演" : "距开抢";
        const citySuffix = `${ent.concert.city}站`;
        const cardTitle =
          ent.concert.artist_name && ent.concert.artist_name.endsWith(citySuffix)
            ? ent.concert.artist_name
            : `${ent.concert.artist_name} · ${citySuffix}`;

        return el(
          "article",
          { className: ent.kind === "sniper" ? "drop-item-box sniper-variant" : "drop-item-box" },
          el(
            "div",
            { className: "flex-row-between" },
            el("span", {
              className: ent.kind === "sniper" ? "badge-inline badge-sniper" : "badge-inline badge-drop",
              text: ent.badge,
            }),
            el(
              "span",
              null,
              el("span", { className: "countdown-prefix", text: countdownPrefix }),
              el("span", {
                className: "countdown-big",
                "data-site-countdown": String(ent.ms),
                text: formatCountdown(ent.ms, Date.now()),
              })
            )
          ),
          el(
            "div",
            null,
            el("strong", { text: cardTitle }),
            el("div", { className: "muted-line", text: `${ent.when} · ${ent.platform} · ${ent.concert.venue}` })
          ),
          el(
            "div",
            { className: "check-strip" },
            ent.kind !== "live_show" ? makeCheck("want", "已点想看") : null,
            ent.kind !== "live_show" ? makeCheck("idcard", "已绑实名证件") : null,
            ent.kind === "live_show"
              ? el(
                  "button",
                  {
                    type: "button",
                    className: isArtistFavorited(ent.concert.artist_name)
                      ? "btn-fav-star-inline is-favorited"
                      : "btn-fav-star-inline",
                    onClick: () => {
                      toggleFavoriteArtist(ent.concert.artist_name);
                      renderDropsSection();
                    },
                  },
                  isArtistFavorited(ent.concert.artist_name) ? "★ 已收藏" : "☆ 收藏歌手"
                )
              : null,
            ent.url
              ? el(
                  "a",
                  { href: ent.url, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" },
                  ent.kind === "sniper" ? "直达蹲回流 ↗" : "前往购票页 ↗"
                )
              : null
          )
        );
      })
    );
  }

  // ---------------- Section 3: Nationwide Directory (List + Monthly Calendar + SVG Map) ----------------

  function getFilteredConcerts() {
    const q = siteState.directoryQuery.trim().toLowerCase();
    return siteState.concerts.filter((c) => {
      if (siteState.onlyFavorites) {
        const favArr = Array.from(siteState.favoriteArtists);
        if (!favArr.some((nm) => concertMatchesArtist(c, nm))) return false;
      }
      if (siteState.selectedCategory !== "all" && (c.artist_category || "cn") !== siteState.selectedCategory) {
        return false;
      }
      if (siteState.selectedRegion !== "all" && c.region !== siteState.selectedRegion) return false;
      if (q) {
        const lineupText = Array.isArray(c.lineup_artists) ? c.lineup_artists.join(" ") : "";
        const hay = `${c.artist_name} ${lineupText} ${c.title} ${c.city} ${c.venue} ${c.platform} ${c.approval_doc_no || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function renderDirectoryViewTabs() {
    const host = document.getElementById("directory-view-tabs");
    if (!host) return;
    const views = [
      ["list", "≡ 排期清单"],
      ["calendar", "◫ 周末月历"],
      ["map", "◎ 城市巡演地图"],
    ];
    setChildren(
      host,
      views.map(([code, label]) =>
        el(
          "button",
          {
            type: "button",
            role: "tab",
            "aria-selected": siteState.directoryView === code ? "true" : "false",
            className: siteState.directoryView === code ? "seg-btn active" : "seg-btn",
            onClick: () => {
              siteState.directoryView = code;
              renderDirectoryViewTabs();
              renderDirectorySection();
            },
          },
          label
        )
      )
    );
  }

  function renderDirectoryCategoryTabs() {
    const bar = document.getElementById("directory-category-tabs");
    if (!bar) return;
    const allCount = siteState.concerts.length;
    const westCount = siteState.concerts.filter((c) => c.artist_category === "intl_west").length;
    const jpkrCount = siteState.concerts.filter((c) => c.artist_category === "intl_jpkr").length;
    const cnCount = siteState.concerts.filter((c) => (c.artist_category || "cn") === "cn").length;
    const cats = [
      ["all", `全部中外阵容 (${allCount})`],
      ["intl_west", `欧美乐队与歌手 (${westCount})`],
      ["intl_jpkr", `日韩乐队与歌手 (${jpkrCount})`],
      ["cn", `华语现场 (${cnCount})`],
    ];
    setChildren(
      bar,
      cats.map(([code, label]) =>
        el(
          "button",
          {
            type: "button",
            role: "tab",
            "aria-selected": siteState.selectedCategory === code ? "true" : "false",
            className: siteState.selectedCategory === code ? "tag-pill active" : "tag-pill",
            onClick: () => {
              siteState.selectedCategory = code;
              renderDirectoryCategoryTabs();
              renderDirectorySection();
            },
          },
          label
        )
      )
    );
  }

  function renderDirectoryRegionTabs() {
    const bar = document.getElementById("directory-region-tabs");
    if (!bar) return;
    setChildren(
      bar,
      Object.entries(siteState.regions).map(([code, label]) =>
        el(
          "button",
          {
            type: "button",
            role: "tab",
            "aria-selected": siteState.selectedRegion === code ? "true" : "false",
            className: siteState.selectedRegion === code ? "tag-pill active" : "tag-pill",
            onClick: () => {
              siteState.selectedRegion = code;
              renderDirectoryRegionTabs();
              renderDirectorySection();
            },
          },
          label
        )
      )
    );
  }

  function renderCalendarView(filtered) {
    const stage = document.getElementById("directory-visual-stage");
    if (!stage) return;

    const byDate = new Map();
    const pushEvt = (dateStr, evt) => {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return;
      if (!byDate.has(dateStr)) byDate.set(dateStr, []);
      byDate.get(dateStr).push(evt);
    };

    for (const c of filtered) {
      const showDate = (c.show_time || "").slice(0, 10);
      pushEvt(showDate, {
        kind: c.status === "approved_pending" ? "approval" : "show",
        label: `${c.city}·${c.artist_name}`,
        desc: `${c.status === "approved_pending" ? "过审拟办" : "演出日"} ${c.show_time} · ${c.venue}`,
        concert: c,
      });
      for (const r of c.ticket_rounds || []) {
        const sDate = (r.sale_time || "").slice(0, 10);
        pushEvt(sDate, {
          kind: "presale",
          label: `抢·${c.artist_name}`,
          desc: `[${r.round_label}] ${r.sale_time}（${r.platform}）· ${c.city}站`,
          concert: c,
        });
      }
    }

    const y = siteState.calYear;
    const m = siteState.calMonth;
    const firstDow = (new Date(Date.UTC(y, m, 1)).getUTCDay() + 6) % 7; // Mon=0..Sun=6
    const daysInMonth = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
    const dows = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

    const cells = [];
    for (let i = 0; i < firstDow; i++) {
      cells.push(el("div", { className: "cal-cell is-empty" }));
    }
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const dowIdx = (firstDow + d - 1) % 7;
      const isWeekend = dowIdx >= 5;
      const evts = byDate.get(dateStr) || [];
      const isSelected = siteState.selectedCalDate === dateStr;
      const cls = ["cal-cell", isWeekend ? "is-weekend" : "", isSelected ? "is-selected" : ""].filter(Boolean).join(" ");

      cells.push(
        el(
          "button",
          {
            type: "button",
            className: cls,
            onClick: () => {
              siteState.selectedCalDate = dateStr;
              renderCalendarView(filtered);
            },
          },
          el(
            "div",
            { className: "cal-day-num" },
            el("span", { text: String(d) }),
            isWeekend ? el("span", { className: "cal-weekend-tag", text: dowIdx === 5 ? "六" : "日" }) : null
          ),
          evts.slice(0, 3).map((ev) =>
            el("div", {
              className: `cal-chip is-${ev.kind}`,
              text: ev.label,
            })
          ),
          evts.length > 3 ? el("div", { className: "muted-line", text: `+${evts.length - 3} 场` }) : null
        )
      );
    }

    const countMonthEvents = (yr, mo) => {
      const prefix = `${yr}-${String(mo + 1).padStart(2, "0")}-`;
      let total = 0;
      for (const [dt, list] of byDate.entries()) {
        if (dt.startsWith(prefix)) total += list.length;
      }
      return total;
    };
    const prevY = m === 0 ? y - 1 : y;
    const prevM = m === 0 ? 11 : m - 1;
    const nextY = m === 11 ? y + 1 : y;
    const nextM = m === 11 ? 0 : m + 1;
    const prevCount = countMonthEvents(prevY, prevM);
    const nextCount = countMonthEvents(nextY, nextM);

    const selectedEvts = byDate.get(siteState.selectedCalDate) || [];

    setChildren(
      stage,
      el(
        "div",
        { className: "cal-shell" },
        el(
          "div",
          { className: "cal-header" },
          el(
            "div",
            { className: "flex-row-wrap" },
            el(
              "button",
              {
                type: "button",
                className: "site-btn site-btn-sm",
                onClick: () => {
                  siteState.calYear = prevY;
                  siteState.calMonth = prevM;
                  renderCalendarView(filtered);
                },
              },
              prevCount > 0 ? `← ${prevM + 1}月 (${prevCount})` : `← 上月`
            ),
            el("strong", { className: "cal-month-title", text: `${y} 年 ${m + 1} 月` }),
            el(
              "button",
              {
                type: "button",
                className: "site-btn site-btn-sm",
                onClick: () => {
                  siteState.calYear = nextY;
                  siteState.calMonth = nextM;
                  renderCalendarView(filtered);
                },
              },
              nextCount > 0 ? `${nextM + 1}月 (${nextCount}) →` : `下月 →`
            ),
            el(
              "button",
              {
                type: "button",
                className: "tag-pill",
                onClick: () => {
                  siteState.calYear = nowShanghai.getUTCFullYear();
                  siteState.calMonth = nowShanghai.getUTCMonth();
                  siteState.selectedCalDate = nowShanghai.toISOString().slice(0, 10);
                  renderCalendarView(filtered);
                },
              },
              "回到本月"
            )
          ),
          el(
            "div",
            { className: "cal-legend" },
            el("span", { className: "cal-legend-item" }, el("span", { className: "cal-swatch is-presale" }), "开票预售"),
            el("span", { className: "cal-legend-item" }, el("span", { className: "cal-swatch is-show" }), "演出日期"),
            el("span", { className: "cal-legend-item" }, el("span", { className: "cal-swatch is-approval" }), "文旅过审")
          )
        ),
        el(
          "div",
          { className: "cal-grid" },
          dows.map((nm, idx) => el("div", { className: idx >= 5 ? "cal-dow is-weekend" : "cal-dow", text: nm })),
          cells
        ),
        el(
          "div",
          { className: "cal-day-detail" },
          el("strong", {
            text: siteState.selectedCalDate
              ? `${siteState.selectedCalDate} 当日排期与开票节点（共 ${selectedEvts.length} 项）`
              : "点击日历中任意标注日期，查看当日演出、预售与跨城预算",
          }),
          selectedEvts.length > 0
            ? selectedEvts.map((ev) =>
                el(
                  "div",
                  { className: "slot-line" },
                  el(
                    "span",
                    null,
                    el("strong", { text: `${ev.concert.artist_name} · ${ev.concert.city}站 ` }),
                    ev.desc
                  ),
                  el(
                    "span",
                    { className: "flex-row-wrap" },
                    el(
                      "button",
                      {
                        type: "button",
                        className: isArtistFavorited(ev.concert.artist_name)
                          ? "btn-fav-star-inline is-favorited"
                          : "btn-fav-star-inline",
                        onClick: () => toggleFavoriteArtist(ev.concert.artist_name),
                      },
                      isArtistFavorited(ev.concert.artist_name) ? "★ 已收藏" : "☆ 收藏"
                    ),
                    el(
                      "a",
                      {
                        href: `/api/public/showcase-ics?id=${encodeURIComponent(ev.concert.id)}&home_city=${encodeURIComponent(siteState.homeCity)}`,
                        className: "tag-pill",
                      },
                      "日历 .ics"
                    )
                  )
                )
              )
            : el("p", { className: "muted-line mt-xs", text: "该日期暂无筛选条件下的演出或开票节点，可点击其他高亮日期或翻看下月。" })
        )
      )
    );
  }

  function renderMapView(filtered) {
    const stage = document.getElementById("directory-visual-stage");
    if (!stage) return;

    const showsByCity = new Map();
    for (const c of filtered) {
      if (!showsByCity.has(c.city)) showsByCity.set(c.city, []);
      showsByCity.get(c.city).push(c);
    }

    const nodes = siteState.cityMapNodes || DEFAULT_CITY_MAP_NODES;
    const originNode = nodes.find((n) => n.city === siteState.homeCity) || nodes.find((n) => n.city === "上海");

    if (!siteState.selectedMapCity || !showsByCity.has(siteState.selectedMapCity)) {
      const firstActive = nodes.find((n) => showsByCity.has(n.city));
      siteState.selectedMapCity = firstActive ? firstActive.city : siteState.homeCity;
    }

    // Stylized clean cartographic outline of China + Hainan
    const svg = svgEl(
      "svg",
      { className: "tour-map-svg", viewBox: "0 0 720 460", role: "img", "aria-label": "中国及港澳巡演城市高铁联动地图" },
      svgEl("path", {
        className: "map-silhouette",
        d: "M128,154 L196,118 L272,110 L356,120 L432,90 L515,64 L608,76 L628,128 L586,162 L566,184 L600,204 L594,234 L628,274 L616,326 L576,374 L526,418 L466,426 L418,402 L370,404 L318,382 L262,366 L216,326 L158,284 L118,228 Z",
      }),
      svgEl("path", {
        className: "map-silhouette",
        d: "M438,434 L462,432 L466,449 L442,452 Z",
      }),
      svgEl("text", { className: "map-region-label", x: "456", y: "114", text: "京津冀" }),
      svgEl("text", { className: "map-region-label", x: "624", y: "234", text: "长三角" }),
      svgEl("text", { className: "map-region-label", x: "576", y: "442", text: "大湾区 / 港澳" }),
      svgEl("text", { className: "map-region-label", x: "242", y: "260", text: "成渝双城" })
    );

    // Draw HSR corridor arcs from origin city to active tour cities
    if (originNode) {
      for (const nd of nodes) {
        if (nd.city === originNode.city || !showsByCity.has(nd.city)) continue;
        const mx = (originNode.x + nd.x) / 2;
        const my = (originNode.y + nd.y) / 2 - 22;
        const isSel = siteState.selectedMapCity === nd.city;
        svg.appendChild(
          svgEl("path", {
            className: isSel ? "map-hsr-arc is-selected" : "map-hsr-arc",
            d: `M${originNode.x},${originNode.y} Q${mx},${my} ${nd.x},${nd.y}`,
          })
        );
      }
    }

    // Draw interactive city hubs with collision-free label placement
    for (const nd of nodes) {
      const cityShows = showsByCity.get(nd.city) || [];
      const isOrigin = originNode && nd.city === originNode.city;
      const isSelected = siteState.selectedMapCity === nd.city;
      const r = cityShows.length > 0 ? Math.min(13.5, 9 + cityShows.length) : 5;
      const dotCls = [
        "map-city-dot",
        cityShows.length > 0 ? "has-shows" : "",
        isOrigin ? "is-origin" : "",
        isSelected ? "is-selected" : "",
      ]
        .filter(Boolean)
        .join(" ");

      const labelDx = typeof nd.lx === "number" ? nd.lx : 12;
      const labelDy = typeof nd.ly === "number" ? nd.ly : 4;
      const labelAnchor = nd.anchor || "start";

      const grp = svgEl(
        "g",
        {
          className: "map-hub-group",
          tabindex: "0",
          role: "button",
          "aria-label": `${nd.city}：${cityShows.length} 场演出`,
          onClick: () => {
            siteState.selectedMapCity = nd.city;
            renderMapView(filtered);
          },
          onKeydown: (ev) => {
            if (ev.key === "Enter" || ev.key === " ") {
              ev.preventDefault();
              siteState.selectedMapCity = nd.city;
              renderMapView(filtered);
            }
          },
        },
        isOrigin ? svgEl("circle", { className: "map-origin-halo", cx: String(nd.x), cy: String(nd.y), r: String(r + 6) }) : null,
        svgEl("circle", { className: dotCls, cx: String(nd.x), cy: String(nd.y), r: String(r) }),
        cityShows.length > 0
          ? svgEl("text", { className: "map-city-count", x: String(nd.x), y: String(nd.y), text: String(cityShows.length) })
          : null,
        svgEl("text", {
          className: "map-city-name",
          x: String(nd.x + labelDx),
          y: String(nd.y + labelDy),
          "text-anchor": labelAnchor,
          text: isOrigin ? `${nd.city}(出发)` : nd.city,
        })
      );
      svg.appendChild(grp);
    }

    const selShows = showsByCity.get(siteState.selectedMapCity) || [];
    const sampleTrip = selShows[0] && selShows[0].trip_estimate;
    const nodeCitySet = new Set(nodes.map((n) => n.city));
    const extraCities = Array.from(showsByCity.keys()).filter((c) => !nodeCitySet.has(c));

    setChildren(
      stage,
      el(
        "div",
        { className: "map-layout" },
        el(
          "div",
          { className: "map-svg-wrap" },
          el(
            "div",
            { className: "flex-row-between" },
            el("strong", { text: `巡演城市热力与 12306 高铁联动图（出发地：${siteState.homeCity}）` }),
            el("span", { className: "muted-line", text: "点击红色数字城市点查看当地场次与预算" })
          ),
          svg,
          extraCities.length > 0
            ? el(
                "div",
                { className: "map-extra-cities" },
                el("span", { className: "muted-line", text: "其他有演出城市：" }),
                extraCities.map((city) => {
                  const cnt = (showsByCity.get(city) || []).length;
                  const active = siteState.selectedMapCity === city;
                  return el(
                    "button",
                    {
                      type: "button",
                      className: active ? "tag-pill active" : "tag-pill",
                      onClick: () => {
                        siteState.selectedMapCity = city;
                        renderMapView(filtered);
                      },
                    },
                    `${city} (${cnt})`
                  );
                })
              )
            : null
        ),
        el(
          "aside",
          { className: "map-side-panel" },
          el(
            "div",
            { className: "flex-row-between" },
            el("strong", { text: `📍 ${siteState.selectedMapCity} · 共 ${selShows.length} 场演出` }),
            selShows.length > 0
              ? el(
                  "button",
                  {
                    type: "button",
                    className: "tag-pill",
                    onClick: () => {
                      const inp = document.getElementById("directory-filter-input");
                      siteState.directoryQuery = siteState.selectedMapCity;
                      if (inp) inp.value = siteState.selectedMapCity;
                      siteState.directoryView = "list";
                      renderDirectoryViewTabs();
                      renderDirectorySection();
                    },
                  },
                  "切到列表仅看该城"
                )
              : null
          ),
          sampleTrip
            ? el("div", {
                className: "budget-total-badge",
                text: sampleTrip.is_cross_city
                  ? `🚄 ${sampleTrip.transport_note}`
                  : `🏠 ${sampleTrip.transport_note}`,
              })
            : null,
          selShows.length > 0
            ? selShows.map((c) =>
                el(
                  "div",
                  { className: "map-city-show-card" },
                  el(
                    "div",
                    { className: "flex-row-between" },
                    el("strong", { text: c.artist_name }),
                    el("span", { className: "tour-date-col", text: (c.show_time || "").slice(0, 10) })
                  ),
                  el("div", { className: "muted-line", text: `${c.venue || "场馆见原页"} · 票价 ${c.price_text || "见官方页"}` }),
                  el("div", { className: "muted-line", text: `来源：${c.data_source || c.platform}` }),
                  el(
                    "div",
                    { className: "flex-row-wrap mt-xs" },
                    el(
                      "button",
                      {
                        type: "button",
                        className: isArtistFavorited(c.artist_name)
                          ? "btn-fav-star-inline is-favorited"
                          : "btn-fav-star-inline",
                        onClick: () => toggleFavoriteArtist(c.artist_name),
                      },
                      isArtistFavorited(c.artist_name) ? "★ 已收藏" : "☆ 收藏提醒"
                    ),
                    el(
                      "a",
                      {
                        href: `/api/public/showcase-ics?id=${encodeURIComponent(c.id)}&home_city=${encodeURIComponent(siteState.homeCity)}`,
                        className: "tag-pill",
                      },
                      "下载 .ics"
                    )
                  )
                )
              )
            : el("p", { className: "muted-line", text: `${siteState.selectedMapCity} 在当前筛选条件下暂无排期，可点击其他带数字的城市圆点。` })
        )
      )
    );
  }

  function renderDirectorySection() {
    const filtered = getFilteredConcerts();
    const stage = document.getElementById("directory-visual-stage");
    const listHost = document.getElementById("directory-table-body");

    if (siteState.directoryView === "calendar") {
      if (stage) stage.hidden = false;
      if (listHost) listHost.hidden = true;
      renderCalendarView(filtered);
      return;
    }

    if (siteState.directoryView === "map") {
      if (stage) stage.hidden = false;
      if (listHost) listHost.hidden = true;
      renderMapView(filtered);
      return;
    }

    if (stage) stage.hidden = true;
    if (listHost) listHost.hidden = false;
    renderDirectoryList(filtered);
  }

  function renderDirectoryList(filteredInput) {
    const host = document.getElementById("directory-table-body");
    if (!host) return;
    const filtered = filteredInput || getFilteredConcerts();

    if (!filtered.length) {
      setChildren(
        host,
        el("div", { className: "watchlist-empty-box", text: "当前筛选条件下暂无排期，请切换城市群、阵容分类或清空搜索词。" })
      );
      return;
    }

    const isFiltered =
      Boolean(siteState.directoryQuery.trim()) ||
      siteState.selectedCategory !== "all" ||
      siteState.selectedRegion !== "all" ||
      siteState.onlyFavorites;
    const DEFAULT_VISIBLE = 12;
    const visibleList =
      !isFiltered && !siteState.directoryExpandedAll && filtered.length > DEFAULT_VISIBLE
        ? filtered.slice(0, DEFAULT_VISIBLE)
        : filtered;

    const rowNodes = visibleList.map((c) => {
        const isExpanded = siteState.expandedConcertId === c.id;
        const rail = c.rail_plan || {};
        const trip = c.trip_estimate || null;
        const guide = c.venue_guide || null;
        const shortSourceLabel =
          c.data_source && c.data_source.includes("秀动")
            ? "秀动实时在售"
            : c.data_source || `${c.platform}实时在售`;
        const statusBadge =
          c.status === "approved_pending"
            ? el("span", { className: "badge-inline badge-approval", text: "文旅过审早鸟" })
            : c.status === "waiting_round2"
              ? el("span", { className: "badge-inline badge-sniper", text: "蹲退票回流" })
              : el("span", { className: "badge-inline badge-drop", text: shortSourceLabel });

        const drawerNode = isExpanded
          ? el(
              "div",
              { className: "tour-drawer" },
              el(
                "div",
                { className: "rail-callout" },
                el("strong", { text: "数据来源与开票时间轴" }),
                el("div", { className: "mt-xs", text: `数据来源：${c.data_source || c.platform}` }),
                c.approval_doc_no
                  ? el("div", { className: "mt-xs", text: `审批文号：${c.approval_doc_no}（${c.approval_source}）` })
                  : null,
                (c.ticket_rounds || []).map((r) =>
                  el("div", { className: "mt-xs", text: `• [${r.round_label}] ${r.sale_time}（${r.platform}）` })
                ),
                (c.refund_tiers || []).map((rf) =>
                  el("div", { className: "mt-xs muted-line", text: `• [${rf.tier_label}] ${rf.cutoff_time}` })
                ),
                c.notes ? el("div", { className: "mt-xs muted-line", text: `说明：${c.notes}` }) : null
              ),
              el(
                "div",
                { className: "rail-callout" },
                el("strong", { text: `跨城 12306 高铁与出行估算（${siteState.homeCity}出发）` }),
                rail.is_cross_city
                  ? el(
                      "div",
                      { className: "mt-xs" },
                      el("div", { text: `路线：${rail.corridor}` }),
                      el("div", { text: `去程（${rail.outbound_travel_date}）12306：${formatRailSaleStatus(rail.outbound_12306_sale_time)}` }),
                      el("div", { text: `返程（${rail.return_travel_date}）12306：${formatRailSaleStatus(rail.return_12306_sale_time)}` }),
                      el("div", { className: "muted-line mt-xs", text: rail.station_batch_tip || "" })
                    )
                  : el("div", {
                      className: "mt-xs muted-line",
                      text: `演出位于你的出发城市（${siteState.homeCity}），无需跨城高铁；可在顶部切换出发地测算跨城出行时间。`,
                    }),
                trip && trip.is_cross_city
                  ? el(
                      "div",
                      { className: "budget-total-badge" },
                      `跨城差旅总花费参考（非票价）：约 ¥${trip.total_weekend_yuan}（含中档票 ¥${trip.ticket_mid_yuan} + 往返高铁 ¥${trip.hsr_roundtrip_yuan} + 1晚住宿 ¥${trip.hotel_1night_yuan}）`
                    )
                  : null
              ),
              el(
                "div",
                { className: "rail-callout" },
                el("strong", { text: guide ? `场馆选座与散场避坑 · ${guide.venue_name}` : "场馆与快捷操作" }),
                guide
                  ? el(
                      "div",
                      { className: "mt-xs" },
                      el("div", { className: "venue-guide-tip", text: `🎯 推荐区位：${guide.best_seats}` }),
                      el("div", { className: "venue-guide-tip mt-xs", text: `⚠️ 避坑提醒：${guide.avoid_tip}` }),
                      el("div", { className: "venue-guide-tip mt-xs", text: `🚇 散场交通：${guide.transit_tip}` })
                    )
                  : el("div", { className: "muted-line mt-xs", text: "优先选择场馆正中二层看台或调音台前方 3 米以获得最均衡的现场声像。" }),
                el(
                  "div",
                  { className: "flex-row-wrap mt-sm" },
                  el(
                    "a",
                    {
                      href: `/api/public/showcase-ics?id=${encodeURIComponent(c.id)}&home_city=${encodeURIComponent(siteState.homeCity)}`,
                      className: "site-btn site-btn-sm",
                    },
                    "下载 .ics"
                  ),
                  el(
                    "button",
                    {
                      type: "button",
                      className: "site-btn site-btn-sm",
                      onClick: () => {
                        const dataUrl = renderStubCanvasDataUrl({
                          city: c.city,
                          date: (c.show_time || "").slice(0, 10),
                          artist: c.artist_name,
                          title: c.title,
                          venue: c.venue,
                          paid: trip ? trip.ticket_mid_yuan : 680,
                          seat: `${c.platform} 意向场次`,
                          rating: 5,
                          acoustics: (guide && guide.best_seats) || "期待完美现场声场！",
                          memory: (guide && guide.transit_tip) || `出发地：${siteState.homeCity}`,
                        });
                        openPngPreviewModal(`${c.artist_name} · ${c.city}站预约票根 (PNG)`, dataUrl, `liveecho-${c.city}-${c.id}.png`);
                      },
                    },
                    "↓ 票根 PNG"
                  ),
                  c.ticket_url
                    ? el("a", { href: c.ticket_url, target: "_blank", rel: "noopener noreferrer", className: "site-btn site-btn-sm" }, "官方页 ↗")
                    : null
                )
              )
            )
          : null;

        return el(
          "div",
          { className: "tour-row" },
          el(
            "div",
            {
              className: "tour-row-summary",
              onClick: () => {
                siteState.expandedConcertId = isExpanded ? null : c.id;
                renderDirectoryList(filtered);
              },
            },
            el("div", { className: "tour-date-col", text: c.show_time }),
            el("div", { className: "tour-city-col", text: c.city }),
            el(
              "div",
              { className: "tour-artist-col" },
              el(
                "div",
                { className: "flex-row-wrap" },
                el("strong", { text: c.artist_name }),
                c.artist_category === "intl_west"
                  ? el("span", { className: "badge-inline badge-intl", text: "欧美来华/港澳" })
                  : c.artist_category === "intl_jpkr"
                    ? el("span", { className: "badge-inline badge-intl", text: "日韩来华/港澳" })
                    : null,
                c.event_kind !== "festival"
                  ? el(
                      "button",
                      {
                        type: "button",
                        className: isArtistFavorited(c.artist_name)
                          ? "btn-fav-star-inline is-favorited"
                          : "btn-fav-star-inline",
                        onClick: (ev) => {
                          ev.stopPropagation();
                          toggleFavoriteArtist(c.artist_name);
                          renderHeroQuickArtists();
                        },
                      },
                      isArtistFavorited(c.artist_name) ? "★ 已收藏" : "☆ 收藏"
                    )
                  : null
              ),
              el("span", { className: "tour-sub-line", text: c.title })
            ),
            el(
              "div",
              null,
              el("div", { text: c.venue || "场馆见原页" }),
              el("div", {
                className: "tour-sub-line",
                text: c.price_text || "票价见官方页",
              })
            ),
            el("div", null, statusBadge),
            el("span", { className: "muted-line", text: isExpanded ? "收起 ▲" : "攻略/高铁 ▼" })
          ),
          drawerNode
        );
      });

    const expandBar =
      !isFiltered && filtered.length > DEFAULT_VISIBLE
        ? el(
            "div",
            { className: "dir-expand-bar" },
            el("span", {
              className: "muted-line",
              text: siteState.directoryExpandedAll
                ? `已展开全部 ${filtered.length} 场实时演出`
                : `当前显示前 ${visibleList.length} 场（共 ${filtered.length} 场实时演出）`,
            }),
            el(
              "button",
              {
                type: "button",
                className: "site-btn site-btn-sm",
                onClick: () => {
                  siteState.directoryExpandedAll = !siteState.directoryExpandedAll;
                  renderDirectoryList(filtered);
                },
              },
              siteState.directoryExpandedAll
                ? `收起为前 ${DEFAULT_VISIBLE} 场 ▲`
                : `展开其余 ${filtered.length - visibleList.length} 场演出 ▼`
            )
          )
        : null;

    setChildren(host, rowNodes, expandBar);
  }

  // ---------------- Section 4: Interactive 3-Step Festival Advisor ----------------

  function getFestivalSelectionSet(festKey) {
    if (!siteState.selectedFestivalBandsByKey[festKey]) {
      siteState.selectedFestivalBandsByKey[festKey] = new Set();
    }
    return siteState.selectedFestivalBandsByKey[festKey];
  }

  function parsePastedTimetableText(rawText, defaultDate) {
    const fallbackDate = /^\d{4}-\d{2}-\d{2}$/.test(defaultDate || "")
      ? defaultDate
      : new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);
    const defaultYear = fallbackDate.slice(0, 4);
    let currentDate = fallbackDate;
    let currentStage = "主舞台";
    const parsed = [];

    const lines = String(rawText || "").split(/\r?\n/);
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;

      // Detect date marker on line (YYYY-MM-DD, MM月DD日, MM.DD, MM/DD)
      const fullDateM = /(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?/.exec(line);
      if (fullDateM) {
        currentDate = `${fullDateM[1]}-${String(fullDateM[2]).padStart(2, "0")}-${String(fullDateM[3]).padStart(2, "0")}`;
      } else {
        const mdM = /(?:^|\s|\[|【)(\d{1,2})(?:月|[./])(\d{1,2})日?(?:\s|\]|】|$)/.exec(line);
        if (mdM) {
          const mo = Number(mdM[1]);
          const dy = Number(mdM[2]);
          if (mo >= 1 && mo <= 12 && dy >= 1 && dy <= 31) {
            currentDate = `${defaultYear}-${String(mo).padStart(2, "0")}-${String(dy).padStart(2, "0")}`;
          }
        }
      }

      // Check for time range HH:MM - HH:MM
      const timeM = /(\d{1,2})[:：](\d{2})\s*[-~—–至]\s*(\d{1,2})[:：](\d{2})/.exec(line);
      if (!timeM) {
        const stageHeaderM = /([\u4e00-\u9fa5A-Za-z0-9·\s]{1,18}(?:舞台|STAGE|Stage|区|厅))/.exec(line);
        if (stageHeaderM) {
          currentStage = stageHeaderM[1].replace(/[【】\[\]：:]/g, "").trim() || currentStage;
        }
        continue;
      }

      const st = `${String(timeM[1]).padStart(2, "0")}:${timeM[2]}`;
      const en = `${String(timeM[3]).padStart(2, "0")}:${timeM[4]}`;
      let rest = line.replace(timeM[0], " ");
      rest = rest
        .replace(/20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?/g, " ")
        .replace(/(?:^|\s|\[|【)\d{1,2}(?:月|[./])\d{1,2}日?(?:\s|\]|】|$)/g, " ");

      let stage = currentStage;
      const inlineStageM = /[【\[]?([\u4e00-\u9fa5A-Za-z0-9·]{1,16}(?:舞台|STAGE|Stage))[】\]：:]?/.exec(rest);
      if (inlineStageM) {
        stage = inlineStageM[1].trim();
        rest = rest.replace(inlineStageM[0], " ");
      }

      const artist = rest
        .replace(/^[|｜·•\-—:：\s]+|[|｜·•\-—:：\s]+$/g, "")
        .replace(/\s+/g, " ")
        .trim();
      if (!artist) continue;

      parsed.push({
        artist,
        stage: stage || "主舞台",
        day_date: currentDate,
        set_start: st,
        set_end: en,
      });
    }
    return parsed;
  }

  function buildFestivalCatalog() {
    const liveFestivals = siteState.concerts.filter((c) => c.event_kind === "festival");
    const catalog = [];

    for (const lf of liveFestivals) {
      const key = `fest-${lf.id}`;
      const bandList = [];
      const seen = new Set();
      const pushBand = (nm) => {
        const clean = String(nm || "").trim();
        if (!clean || clean === "待定" || clean === "群星" || clean === "阵容见秀动原页") return;
        const k = clean.toLowerCase();
        if (!seen.has(k)) {
          seen.add(k);
          bandList.push(clean);
        }
      };

      for (const b of lf.headliners || []) pushBand(b);
      for (const b of lf.lineup_artists || []) pushBand(b);
      for (const slot of lf.lineup || []) pushBand(slot && slot.artist);
      for (const slot of siteState.customFestivalSlots[key] || []) pushBand(slot && slot.artist);

      const baseSlots = (lf.lineup || []).filter((s) => s && s.artist && s.set_start && s.set_end);
      catalog.push({
        key,
        isDemo: false,
        concertId: lf.id,
        title: lf.festival_name || lf.title,
        city: lf.city || "待定",
        venue: lf.venue || "场馆见原页",
        showTime: lf.show_time || "",
        defaultDate: (lf.show_time || "").slice(0, 10),
        priceText: lf.price_text || "票价见原页",
        ticketUrl: lf.ticket_url || "",
        dataSource: lf.data_source || "秀动 ShowStart 实时在售",
        headliners: (lf.headliners || []).length > 0 ? lf.headliners.slice(0, 5) : bandList.slice(0, 5),
        bands: bandList,
        baseSlots,
      });
    }

    const demoFest = siteState.festivalDemo;
    if (demoFest && Array.isArray(demoFest.lineup) && demoFest.lineup.length > 0) {
      const demoBands = Array.from(new Set(demoFest.lineup.map((s) => s.artist).filter(Boolean)));
      catalog.push({
        key: "demo-simulator",
        isDemo: true,
        concertId: demoFest.id || 990001,
        title: demoFest.festival_name || "双舞台撞场测算演示（示例排期 · 非实时官宣）",
        city: demoFest.city || "示例",
        venue: demoFest.venue || "户外双舞台示例",
        showTime: (demoFest.lineup[0] && demoFest.lineup[0].day_date) || "",
        defaultDate: (demoFest.lineup[0] && demoFest.lineup[0].day_date) || "",
        priceText: demoFest.price_text || "示例单日票",
        ticketUrl: "",
        dataSource: "交互模拟器演示 · 非真实官宣",
        bands: demoBands,
        baseSlots: demoFest.lineup.slice(),
      });
    }

    return catalog;
  }

  function renderFestivalSection() {
    const toggleHost = document.getElementById("festival-band-toggles");
    const outHost = document.getElementById("festival-decision-output");
    if (!toggleHost || !outHost) return;

    const catalog = buildFestivalCatalog();
    const realCount = catalog.filter((f) => !f.isDemo).length;
    if (siteState.selectedFestivalKey && !catalog.some((f) => f.key === siteState.selectedFestivalKey)) {
      siteState.selectedFestivalKey = "";
    }
    const activeFest = catalog.find((f) => f.key === siteState.selectedFestivalKey) || null;

    // STEP 01: Festival Picker Cards
    setChildren(
      toggleHost,
      el("div", {
        className: "festival-step-label",
        text: `STEP 01 · 先选择一场音乐节（当前秀动实时在售 ${realCount} 场 · 默认不预选）`,
      }),
      el(
        "div",
        { className: "festival-picker-grid" },
        catalog.map((f) => {
          const isSelected = activeFest && activeFest.key === f.key;
          const customCount = (siteState.customFestivalSlots[f.key] || []).filter(
            (s) => s.set_start && s.set_end
          ).length;
          const totalTimedSlots = f.baseSlots.length + customCount;
          const selCount = getFestivalSelectionSet(f.key).size;

          const statusTag = f.isDemo
            ? "示例演练 · 含示范时刻表"
            : totalTimedSlots > 0
              ? `已录入 ${totalTimedSlots} 条时段`
              : f.bands.length > 0
                ? `完整阵容 ${f.bands.length} 组`
                : "秀动原页阵容待补";

          // Surface favorited artists first, then ranked major headliners right on the card!
          const favMatches = f.bands.filter((b) => isArtistFavorited(b));
          const cardLineupPreview = [];
          const previewSeen = new Set();
          for (const b of favMatches.concat(f.headliners || f.bands)) {
            const bk = b.toLowerCase();
            if (!previewSeen.has(bk)) {
              previewSeen.add(bk);
              cardLineupPreview.push(b);
            }
            if (cardLineupPreview.length >= 5) break;
          }
          const remainingCount = Math.max(0, f.bands.length - cardLineupPreview.length);

          return el(
            "button",
            {
              type: "button",
              className: [
                "festival-picker-card",
                isSelected ? "active" : "",
                f.isDemo ? "is-demo-card" : "",
              ]
                .filter(Boolean)
                .join(" "),
              "aria-pressed": isSelected ? "true" : "false",
              onClick: () => {
                siteState.selectedFestivalKey = isSelected ? "" : f.key;
                renderFestivalSection();
              },
            },
            el(
              "div",
              { className: "festival-picker-head" },
              el("span", {
                className: f.isDemo ? "badge-inline badge-approval" : "badge-inline badge-intl",
                text: f.isDemo ? "非真实官宣 · 演示" : `${f.city} · 秀动实时`,
              }),
              el("span", { className: "muted-line", text: statusTag })
            ),
            el("div", { className: "festival-picker-title", text: f.title }),
            cardLineupPreview.length > 0
              ? el(
                  "div",
                  { className: "festival-card-headliners" },
                  cardLineupPreview.map((artist) => {
                    const isFav = isArtistFavorited(artist);
                    return el("span", {
                      className: isFav ? "headliner-chip is-fav" : "headliner-chip",
                      text: isFav ? `★ ${artist}` : artist,
                    });
                  }),
                  remainingCount > 0
                    ? el("span", { className: "headliner-chip is-more", text: `+${remainingCount} 组` })
                    : null
                )
              : !f.isDemo
                ? el("div", { className: "festival-picker-meta", text: "秀动原页暂未填报具体乐队名单" })
                : null,
            el("div", {
              className: "festival-picker-meta",
              text: f.isDemo
                ? "点击体验双舞台重叠撞场与最值单日票算法"
                : `${f.showTime ? f.showTime.slice(0, 16) : "待定"} · ${f.priceText}${selCount > 0 ? ` · 已勾 ${selCount} 组` : ""}`,
            })
          );
        })
      )
    );

    // If user hasn't picked a festival yet, prompt clearly
    if (!activeFest) {
      setChildren(
        outHost,
        el(
          "div",
          { className: "rec-highlight" },
          "请先在上方 STEP 01 点击选择一场音乐节，随后将展开该场全部参演乐队供你勾选与撞场测算（默认不预选任何音乐节与乐队）。"
        )
      );
      return;
    }

    const selectedSet = getFestivalSelectionSet(activeFest.key);
    siteState.selectedFestivalBands = selectedSet;

    // Combine base timetable slots + user-entered custom slots for this festival
    const customList = siteState.customFestivalSlots[activeFest.key] || [];
    const mergedSlotMap = new Map();
    for (const s of activeFest.baseSlots) {
      mergedSlotMap.set(`${s.artist}|${s.day_date || ""}`, { ...s });
    }
    for (const s of customList) {
      if (s && s.artist && s.set_start && s.set_end) {
        mergedSlotMap.set(`${s.artist}|${s.day_date || activeFest.defaultDate}`, {
          artist: s.artist,
          stage: s.stage || "主舞台",
          day_date: s.day_date || activeFest.defaultDate || "待定日期",
          set_start: s.set_start,
          set_end: s.set_end,
        });
      }
    }
    const effectiveSlots = Array.from(mergedSlotMap.values());

    // Build complete band list (including any bands added via pasted timetable)
    const allBands = activeFest.bands.slice();
    const bandKeys = new Set(allBands.map((b) => b.toLowerCase()));
    for (const s of effectiveSlots) {
      if (s.artist && !bandKeys.has(s.artist.toLowerCase())) {
        bandKeys.add(s.artist.toLowerCase());
        allBands.push(s.artist);
      }
    }

    // Compute single-day recommendation & clashes from effectiveSlots
    const byDay = new Map();
    for (const slot of effectiveSlots) {
      const dk = slot.day_date || activeFest.defaultDate || "待定日期";
      if (!byDay.has(dk)) byDay.set(dk, []);
      byDay.get(dk).push(slot);
    }

    let bestDay = "";
    let bestHits = [];
    const clashes = [];
    const tightSwitches = [];

    for (const [day, slots] of byDay.entries()) {
      const favSlots = slots.filter((s) => selectedSet.has(s.artist));
      if (favSlots.length > bestHits.length) {
        bestDay = day;
        bestHits = favSlots.map((s) => s.artist);
      }
      for (let i = 0; i < favSlots.length; i++) {
        const a = favSlots[i];
        const st1 = hhmmToMinutes(a.set_start);
        let en1 = hhmmToMinutes(a.set_end);
        if (st1 === null || en1 === null) continue;
        if (en1 <= st1) en1 += 1440;
        for (let j = i + 1; j < favSlots.length; j++) {
          const b = favSlots[j];
          const st2 = hhmmToMinutes(b.set_start);
          let en2 = hhmmToMinutes(b.set_end);
          if (st2 === null || en2 === null) continue;
          if (en2 <= st2) en2 += 1440;
          const overlap = Math.min(en1, en2) - Math.max(st1, st2);
          if (overlap > 0) {
            clashes.push(
              `${day} 撞场告警：${a.artist}（${a.stage} ${a.set_start}-${a.set_end}）与 ${b.artist}（${b.stage} ${b.set_start}-${b.set_end}）重叠 ${overlap} 分钟！`
            );
          } else if (overlap >= -15 && a.stage !== b.stage) {
            tightSwitches.push(
              `${day} 极限换场：${a.artist}（${a.stage} ${a.set_start}-${a.set_end}）与 ${b.artist}（${b.stage} ${b.set_start}-${b.set_end}）跨舞台仅差 ${-overlap} 分钟`
            );
          }
        }
      }
    }

    const upsertCustomSlot = (bandName, patch) => {
      const list = siteState.customFestivalSlots[activeFest.key]
        ? siteState.customFestivalSlots[activeFest.key].slice()
        : [];
      const idx = list.findIndex((x) => x.artist === bandName);
      const base =
        idx >= 0
          ? list[idx]
          : {
              artist: bandName,
              day_date: activeFest.defaultDate || "",
              stage: "主舞台",
              set_start: "",
              set_end: "",
            };
      const updated = { ...base, ...patch };
      if (idx >= 0) {
        list[idx] = updated;
      } else {
        list.push(updated);
      }
      siteState.customFestivalSlots[activeFest.key] = list;
    };

    const getCustomSlotForBand = (bandName) => {
      const list = siteState.customFestivalSlots[activeFest.key] || [];
      const found = list.find((x) => x.artist === bandName);
      if (found) return found;
      const fromBase = activeFest.baseSlots.find((x) => x.artist === bandName);
      if (fromBase) return fromBase;
      return {
        artist: bandName,
        day_date: activeFest.defaultDate || "",
        stage: "主舞台",
        set_start: "",
        set_end: "",
      };
    };

    // STEP 02: Full Band Selection Panel for Selected Festival
    const step2Panel = el(
      "div",
      { className: "festival-band-panel" },
      el("div", {
        className: "festival-step-label",
        text: `STEP 02 · 从「${activeFest.title}」完整阵容中勾选想看的乐队（共 ${allBands.length} 组 · 已选 ${selectedSet.size} 组）`,
      }),
      el(
        "div",
        { className: "flex-row-between" },
        el(
          "div",
          null,
          el("strong", { text: activeFest.title }),
          el("span", {
            className: "muted-line",
            text: ` · ${activeFest.city} · ${activeFest.venue} · ${activeFest.showTime || "日期见原页"} · ${activeFest.priceText}`,
          })
        ),
        activeFest.ticketUrl
          ? el(
              "a",
              {
                href: activeFest.ticketUrl,
                target: "_blank",
                rel: "noopener noreferrer",
                className: "tag-pill",
              },
              "秀动原页核验/购票 ↗"
            )
          : el("span", { className: "badge-inline badge-approval", text: "交互模拟器演示 · 非真实官宣" })
      ),
      allBands.length > 0
        ? el(
            "div",
            { className: "festival-band-actions" },
            el(
              "button",
              {
                type: "button",
                className: "site-btn site-btn-sm",
                onClick: () => {
                  for (const b of allBands) selectedSet.add(b);
                  renderFestivalSection();
                },
              },
              `✓ 全选全部 (${allBands.length} 组)`
            ),
            el(
              "button",
              {
                type: "button",
                className: "site-btn site-btn-sm",
                onClick: () => {
                  let matched = 0;
                  for (const b of allBands) {
                    const low = b.toLowerCase();
                    const hit = Array.from(siteState.favoriteArtists).some((fav) => {
                      const fl = fav.toLowerCase();
                      return fl && (low.includes(fl) || fl.includes(low));
                    });
                    if (hit) {
                      selectedSet.add(b);
                      matched += 1;
                    }
                  }
                  renderFestivalSection();
                  showSiteToast(
                    matched > 0
                      ? `已从你的收藏名单中自动勾选 ${matched} 组参演乐队`
                      : "你当前收藏的歌手暂未出现在该音乐节阵容中，可直接点击下方乐队勾选"
                  );
                },
              },
              "★ 匹配我收藏的歌手"
            ),
            selectedSet.size > 0
              ? el(
                  "button",
                  {
                    type: "button",
                    className: "site-btn site-btn-sm",
                    onClick: () => {
                      let added = 0;
                      for (const b of selectedSet) {
                        if (!isArtistFavorited(b)) {
                          siteState.favoriteArtists.add(b);
                          added += 1;
                        }
                      }
                      syncStateToUrl();
                      renderHeroKpiStrip();
                      renderHeroQuickArtists();
                      renderWatchlistSection();
                      renderDirectorySection();
                      renderFestivalSection();
                      showSiteToast(added > 0 ? `已将 ${added} 组乐队加入收藏预售雷达` : "已选乐队均已在你的收藏名单中");
                    },
                  },
                  `☆ 收藏已选乐队 (${selectedSet.size})`
                )
              : null,
            selectedSet.size > 0
              ? el(
                  "button",
                  {
                    type: "button",
                    className: "site-btn site-btn-sm",
                    onClick: () => {
                      selectedSet.clear();
                      renderFestivalSection();
                    },
                  },
                  "清空已选"
                )
              : null
          )
        : null,
      allBands.length > 0
        ? el(
            "div",
            { className: "festival-band-pills" },
            allBands.map((band) => {
              const active = selectedSet.has(band);
              const favMark = isArtistFavorited(band) ? "★ " : "";
              return el(
                "button",
                {
                  type: "button",
                  className: active ? "tag-pill active" : "tag-pill",
                  onClick: () => {
                    if (active) {
                      selectedSet.delete(band);
                    } else {
                      selectedSet.add(band);
                    }
                    renderFestivalSection();
                  },
                },
                active ? `✓ ${favMark}${band}` : `+ ${favMark}${band}`
              );
            })
          )
        : el("div", {
            className: "festival-honest-note mt-sm",
            text: "秀动原页暂未填报具体乐队名单；可在下方 STEP 03 直接粘贴官方时刻表文本，系统会自动提取乐队并测算撞场。",
          })
    );

    // STEP 03: Stage Timetable & Real Clash Result Panel
    const step3Nodes = [
      el("div", {
        className: "festival-step-label",
        text: "STEP 03 · 分舞台时段与撞场测算结果",
      }),
    ];

    if (effectiveSlots.length > 0) {
      const selectedArray = Array.from(selectedSet);
      const timedSelectedCount = effectiveSlots.filter((s) => selectedSet.has(s.artist)).length;
      step3Nodes.push(
        el("div", {
          className: "rec-highlight",
          text:
            selectedSet.size === 0
              ? `当前已加载 ${effectiveSlots.length} 条分舞台时段 — 请在上方 STEP 02 勾选 2 组以上乐队即可自动计算撞场与最值单日票`
              : bestDay
                ? `单日票推荐：你勾选的 ${selectedArray.length} 组乐队中，${bestDay} 重合度最高（命中 ${bestHits.length} 组：${bestHits.join("、")}）${clashes.length === 0 && timedSelectedCount >= 2 ? " · 当前无撞场冲突 ✓" : ""}`
                : `已选 ${selectedArray.length} 组乐队（${selectedArray.join("、")}），但尚未给这些乐队填入分舞台时段，请在下方补录时段后测算`,
        })
      );
      for (const cl of clashes) {
        step3Nodes.push(el("div", { className: "clash-highlight", text: cl }));
      }
      for (const ts of tightSwitches) {
        step3Nodes.push(el("div", { className: "festival-honest-note", text: ts }));
      }
      step3Nodes.push(
        el(
          "div",
          { className: "timetable-columns" },
          Array.from(byDay.entries()).map(([day, slots]) =>
            el(
              "div",
              { className: "timetable-day-col" },
              el("strong", { text: `${activeFest.isDemo ? "示例日程" : "演出日程"} ${day}` }),
              slots
                .slice()
                .sort((a, b) => (a.set_start || "").localeCompare(b.set_start || ""))
                .map((s) => {
                  const isFav = selectedSet.has(s.artist);
                  return el(
                    "div",
                    { className: "slot-line" },
                    el(
                      "span",
                      { className: isFav ? "slot-fav-mark" : "" },
                      `${isFav ? "★ " : ""}${s.artist} · ${s.stage || "待定舞台"}`
                    ),
                    el("span", { className: "tour-date-col", text: `${s.set_start}-${s.set_end}` })
                  );
                })
            )
          )
        )
      );
    } else if (!activeFest.isDemo) {
      const selectedArr = Array.from(selectedSet);
      step3Nodes.push(
        el("div", {
          className: "festival-honest-note",
          text:
            selectedArr.length > 0
              ? `已选 ${selectedArr.length} 组乐队（${selectedArr.join("、")}）。秀动公开页目前仅公布完整阵容与总演出时间，尚未发布各舞台逐组时段表（系统绝不虚构撞场时间）。你可以直接在下方填入或粘贴主办方微博/公众号发布的时刻表，立即测算本场是否撞场。`
              : "秀动公开页目前仅公布完整阵容与总演出时间，尚未发布各舞台逐组时段表（系统绝不虚构时间）。先在上方 STEP 02 勾选想看的乐队，即可在下方录入或粘贴官宣时刻表实时测算撞场。",
        })
      );
    }

    // For real live festivals, provide inline stage/time editor + photo upload Vision OCR + official timetable paste box
    if (!activeFest.isDemo) {
      const selectedArr = Array.from(selectedSet);
      const photoState = siteState.festivalPhotoState[activeFest.key] || null;
      const pasteDraft = siteState.festivalPasteDrafts[activeFest.key] || "";
      const pasteInput = el("textarea", {
        className: "festival-paste-area",
        placeholder:
          "直接粘贴微博/公众号/秀动详情里的官宣分舞台时刻表（每行一条），例如：\n2026-11-28\n草莓舞台 万能青年旅店 20:10-21:00\n爱舞台 回春丹乐队 20:20-21:00",
        value: pasteDraft,
        onInput: (ev) => {
          siteState.festivalPasteDrafts[activeFest.key] = ev.target.value;
        },
      });
      pasteInput.value = pasteDraft;

      const matchCanonicalBand = (rawName) => {
        const clean = String(rawName || "").trim();
        if (!clean) return "";
        const low = clean.toLowerCase();
        const exact = allBands.find((b) => b.toLowerCase() === low);
        if (exact) return exact;
        const partial = allBands.find((b) => b.toLowerCase().includes(low) || low.includes(b.toLowerCase()));
        return partial || clean;
      };

      const mergeParsedSlotsIntoFestival = (slotsList) => {
        const existing = siteState.customFestivalSlots[activeFest.key]
          ? siteState.customFestivalSlots[activeFest.key].slice()
          : [];
        for (const slot of slotsList) {
          const canonArtist = matchCanonicalBand(slot.artist);
          const cleanSlot = {
            artist: canonArtist,
            stage: slot.stage || "主舞台",
            day_date: slot.day_date || activeFest.defaultDate || "",
            set_start: slot.set_start || "",
            set_end: slot.set_end || "",
          };
          const idx = existing.findIndex(
            (x) => x.artist.toLowerCase() === canonArtist.toLowerCase() && x.day_date === cleanSlot.day_date
          );
          if (idx >= 0) {
            existing[idx] = cleanSlot;
          } else {
            existing.push(cleanSlot);
          }
          selectedSet.add(canonArtist);
        }
        siteState.customFestivalSlots[activeFest.key] = existing;
      };

      const runFestivalPhotoAnalysis = async (filename, dataUrl) => {
        siteState.festivalPhotoState[activeFest.key] = {
          filename: filename || "timetable.png",
          rawDataUrl: dataUrl,
          previewDataUrl: dataUrl,
          loading: true,
          expanded: false,
          ocrMode: "",
          statusMsg: "正在安全剥离 EXIF 隐私元数据并识别海报分舞台时刻表…",
          slotCount: 0,
        };
        renderFestivalSection();

        try {
          const res = await apiPost("/api/public/parse-festival-photo", {
            filename: filename || "timetable.png",
            image_base64: dataUrl,
            festival_name: activeFest.title,
            default_date: activeFest.defaultDate,
            known_bands: allBands.slice(0, 40),
            vision_api_key: siteState.sessionVisionApiKey || "",
          });

          const recognizedSlots = Array.isArray(res.slots) ? res.slots : [];
          if (res.extracted_text) {
            siteState.festivalPasteDrafts[activeFest.key] = res.extracted_text;
          }
          if (recognizedSlots.length > 0) {
            mergeParsedSlotsIntoFestival(recognizedSlots);
          }

          siteState.festivalPhotoState[activeFest.key] = {
            filename: filename || "timetable.png",
            rawDataUrl: dataUrl,
            previewDataUrl: res.preview_data_url || dataUrl,
            loading: false,
            expanded: false,
            ocrMode: res.ocr_mode || "preview_only",
            width: res.width || 0,
            height: res.height || 0,
            slotCount: recognizedSlots.length,
            statusMsg:
              recognizedSlots.length > 0
                ? `识图成功（${res.ocr_mode === "gemini_vision" ? "Gemini Vision" : res.ocr_mode === "local_rapidocr" ? "本地免费中文 OCR · PP-OCRv6" : res.ocr_mode === "local_tesseract" ? "本地 OCR" : "海报内置时段"}）：已自动提取 ${recognizedSlots.length} 条分舞台时段并完成撞场测算！`
                : res.warning || "照片已安全净化并生成对照预览，请核对后在下方补录时段。",
          };
          renderFestivalSection();
          showSiteToast(
            recognizedSlots.length > 0
              ? `照片识图完成：提取到 ${recognizedSlots.length} 条真实舞台时段并已更新撞场结果！`
              : "照片已安全净化并载入对照预览（未自动检出时段时可填入 Vision Key 或对照补录）"
          );
        } catch (err) {
          const isOffline =
            typeof window.__LIVE_ECHO_STATIC_SHOWCASE__ !== "undefined" ||
            String((err && err.message) || "").includes("Failed to fetch");
          siteState.festivalPhotoState[activeFest.key] = {
            filename: filename || "timetable.png",
            rawDataUrl: dataUrl,
            previewDataUrl: dataUrl,
            loading: false,
            expanded: false,
            ocrMode: isOffline ? "offline_preview" : "error",
            slotCount: 0,
            statusMsg: isOffline
              ? "当前为离线静态页，已为你加载高清时刻表照片对照预览（点击图片可放大）；在线 AI 自动识图请使用 Render / 本地完整实时网页版。"
              : `图片分析失败：${(err && err.message) || "请确认图片为 PNG/JPG/WEBP 且不超过 5MB"}`,
          };
          renderFestivalSection();
          showSiteToast(isOffline ? "已载入本地照片高清预览" : (err && err.message) || "图片分析失败", !isOffline);
        }
      };

      const handleSelectedPhotoFile = (file) => {
        if (!file) return;
        const allowedMimes = ["image/png", "image/jpeg", "image/webp"];
        if (file.type && !allowedMimes.includes(file.type)) {
          showSiteToast("仅支持 PNG、JPG/JPEG 或 WEBP 格式的时刻表照片", true);
          return;
        }
        if (file.size > 5 * 1024 * 1024) {
          showSiteToast("照片超过 5MB 安全上限，请压缩后再上传", true);
          return;
        }
        const reader = new FileReader();
        reader.onload = () => {
          runFestivalPhotoAnalysis(file.name || "timetable.png", String(reader.result || ""));
        };
        reader.readAsDataURL(file);
      };

      // Expose active photo handler for global Ctrl+V clipboard image paste
      siteState._activeFestivalPhotoDropHandler = handleSelectedPhotoFile;

      const fileInput = el("input", {
        type: "file",
        accept: "image/png,image/jpeg,image/webp",
        className: "hidden-file-input",
        "aria-label": "上传音乐节时刻表照片",
        onChange: (ev) => {
          if (ev.target.files && ev.target.files[0]) {
            handleSelectedPhotoFile(ev.target.files[0]);
            ev.target.value = "";
          }
        },
      });

      const dropzone = el(
        "div",
        {
          className: "festival-photo-dropzone",
          role: "button",
          tabIndex: 0,
          onClick: () => fileInput.click(),
          onKeydown: (ev) => {
            if (ev.key === "Enter" || ev.key === " ") {
              ev.preventDefault();
              fileInput.click();
            }
          },
          onDragover: (ev) => {
            ev.preventDefault();
            dropzone.classList.add("is-dragover");
          },
          onDragleave: () => {
            dropzone.classList.remove("is-dragover");
          },
          onDrop: (ev) => {
            ev.preventDefault();
            dropzone.classList.remove("is-dragover");
            if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0]) {
              handleSelectedPhotoFile(ev.dataTransfer.files[0]);
            }
          },
        },
        el("strong", {
          text:
            photoState && photoState.loading
              ? "⏳ 正在安全净化并识别时刻表照片…"
              : "📷 点击上传音乐节时刻表海报 / 拖拽图片至此 / 直接 Ctrl+V 粘贴截图",
        }),
        el("div", {
          className: "muted-line mt-xs",
          text: siteState.localOcrAvailable
            ? "✅ 已内置 0 元免 Key 本地中文识图引擎（PP-OCRv6 离线运行 · 不上传第三方 · 支持 PNG/JPG/WEBP 最大 5MB · 自动剥离 EXIF）"
            : siteState.visionOcrAvailable
              ? "支持 PNG · JPG · WEBP（最大 5MB · 自动剥离 EXIF 隐私信息 · 已就绪自动 Vision 识图）"
              : "支持 PNG · JPG · WEBP（最大 5MB · 内存中安全剥离 EXIF 不落盘 · 支持高清对照预览或填临时 Vision Key 自动识图）",
        })
      );

      const visionKeyInput = !siteState.visionOcrAvailable
        ? el("input", {
            type: "password",
            autocomplete: "off",
            className: "festival-photo-key-input",
            placeholder: "可选：填入 Gemini Vision API Key 开启全自动识图（仅本次页面内存生效，不存本地）",
            value: siteState.sessionVisionApiKey || "",
            onInput: (ev) => {
              siteState.sessionVisionApiKey = ev.target.value.trim();
            },
          })
        : null;
      if (visionKeyInput) visionKeyInput.value = siteState.sessionVisionApiKey || "";

      const photoSection = el(
        "div",
        { className: "festival-photo-box" },
        el(
          "div",
          { className: "flex-row-between" },
          el("strong", { text: "方式一 · 上传官方时刻表照片自动识图分析（支持微博/小红书长图截图）：" }),
          photoState
            ? el(
                "button",
                {
                  type: "button",
                  className: "site-btn site-btn-sm",
                  onClick: () => {
                    delete siteState.festivalPhotoState[activeFest.key];
                    renderFestivalSection();
                  },
                },
                "清除照片"
              )
            : null
        ),
        fileInput,
        dropzone,
        !siteState.visionOcrAvailable
          ? el(
              "div",
              { className: "festival-photo-key-row" },
              visionKeyInput,
              photoState && photoState.rawDataUrl && !photoState.loading
                ? el(
                    "button",
                    {
                      type: "button",
                      className: "site-btn site-btn-sm site-btn-primary",
                      onClick: () => {
                        if (!siteState.sessionVisionApiKey) {
                          showSiteToast("请先在左侧填入 Gemini Vision API Key 再点击重新识图", true);
                          return;
                        }
                        runFestivalPhotoAnalysis(photoState.filename, photoState.rawDataUrl);
                      },
                    },
                    "用此 Key 重新识图"
                  )
                : null
            )
          : null,
        photoState
          ? el(
              "div",
              { className: "festival-photo-preview-wrap" },
              el("div", {
                className: photoState.slotCount > 0 ? "rec-highlight" : "muted-line",
                text: photoState.statusMsg,
              }),
              photoState.previewDataUrl
                ? el("img", {
                    src: photoState.previewDataUrl,
                    alt: `${activeFest.title} 时刻表照片预览`,
                    className: photoState.expanded
                      ? "festival-photo-preview-img is-expanded"
                      : "festival-photo-preview-img",
                    title: photoState.expanded ? "点击收起预览" : "点击展开高清大图对照",
                    onClick: () => {
                      photoState.expanded = !photoState.expanded;
                      renderFestivalSection();
                    },
                  })
                : null
            )
          : null
      );

      step3Nodes.push(
        el(
          "div",
          { className: "festival-slot-editor" },
          el(
            "div",
            { className: "flex-row-between" },
            el("strong", {
              text:
                selectedArr.length > 0
                  ? `为已选 ${selectedArr.length} 组乐队录入真实分舞台时段（填写后自动测算撞场）`
                  : "导入或录入本场真实分舞台时刻表",
            }),
            customList.length > 0
              ? el(
                  "button",
                  {
                    type: "button",
                    className: "site-btn site-btn-sm",
                    onClick: () => {
                      delete siteState.customFestivalSlots[activeFest.key];
                      renderFestivalSection();
                      showSiteToast("已清空本场自定义分舞台时段");
                    },
                  },
                  "清空已录入时段"
                )
              : null
          ),
          selectedArr.length > 0
            ? el(
                "div",
                { className: "mt-xs" },
                selectedArr.map((band) => {
                  const cur = getCustomSlotForBand(band);
                  const dateInp = el("input", {
                    type: "date",
                    className: "festival-slot-input",
                    "aria-label": `${band} 演出日期`,
                    value: cur.day_date || activeFest.defaultDate || "",
                    onChange: (ev) => {
                      upsertCustomSlot(band, { day_date: ev.target.value });
                      renderFestivalSection();
                    },
                  });
                  dateInp.value = cur.day_date || activeFest.defaultDate || "";

                  const stageInp = el("input", {
                    type: "text",
                    className: "festival-slot-input",
                    placeholder: "舞台名（如草莓舞台）",
                    "aria-label": `${band} 舞台`,
                    value: cur.stage || "",
                    onChange: (ev) => {
                      upsertCustomSlot(band, { stage: ev.target.value.trim() || "主舞台" });
                      renderFestivalSection();
                    },
                  });
                  stageInp.value = cur.stage || "";

                  const startInp = el("input", {
                    type: "time",
                    className: "festival-slot-input",
                    "aria-label": `${band} 开始时间`,
                    value: cur.set_start || "",
                    onChange: (ev) => {
                      upsertCustomSlot(band, { set_start: ev.target.value });
                      renderFestivalSection();
                    },
                  });
                  startInp.value = cur.set_start || "";

                  const endInp = el("input", {
                    type: "time",
                    className: "festival-slot-input",
                    "aria-label": `${band} 结束时间`,
                    value: cur.set_end || "",
                    onChange: (ev) => {
                      upsertCustomSlot(band, { set_end: ev.target.value });
                      renderFestivalSection();
                    },
                  });
                  endInp.value = cur.set_end || "";

                  return el(
                    "div",
                    { className: "festival-slot-editor-row" },
                    el("strong", { text: band }),
                    dateInp,
                    stageInp,
                    startInp,
                    endInp
                  );
                })
              )
            : el("p", {
                className: "muted-line mt-xs",
                text: "在上方 STEP 02 勾选乐队后，这里会出现逐组快速填表栏；也可以直接上传时刻表照片或批量粘贴文本。",
              }),
          photoSection,
          el(
            "div",
            { className: "festival-paste-box" },
            el("strong", { text: "方式二 · 或批量粘贴官方时刻表文本（自动识别日期 / 舞台 / 乐队 / 起止时间）：" }),
            pasteInput,
            el(
              "div",
              { className: "flex-row-wrap" },
              el(
                "button",
                {
                  type: "button",
                  className: "site-btn site-btn-sm site-btn-primary",
                  onClick: () => {
                    const txt = (siteState.festivalPasteDrafts[activeFest.key] || "").trim();
                    if (!txt) {
                      showSiteToast("请先粘贴包含起止时间（如 20:10-21:00）的官方时刻表文本", true);
                      return;
                    }
                    const parsed = parsePastedTimetableText(txt, activeFest.defaultDate);
                    if (!parsed.length) {
                      showSiteToast("未识别到「乐队 + HH:MM-HH:MM」格式，请检查时间格式后重试", true);
                      return;
                    }
                    mergeParsedSlotsIntoFestival(parsed);
                    renderFestivalSection();
                    showSiteToast(`已解析并载入 ${parsed.length} 条真实舞台时段，已自动更新撞场测算！`);
                  },
                },
                "解析时刻表并测算本场撞场"
              )
            )
          )
        )
      );
    } else {
      siteState._activeFestivalPhotoDropHandler = null;
    }

    setChildren(outHost, step2Panel, step3Nodes);
  }

  // ---------------- Section 5: Culture Bureau Early Approvals ----------------

  function renderApprovalsSection() {
    const grid = document.getElementById("approvals-ledger");
    const portalRow = document.getElementById("culture-portal-links");
    if (!grid || !portalRow) return;

    const approvals = siteState.concerts.filter((c) => c.status === "approved_pending");
    setChildren(
      grid,
      approvals.length > 0
        ? approvals.map((ap) =>
            el(
              "article",
              { className: "approval-box" },
              el(
                "div",
                { className: "flex-row-between" },
                el("span", { className: "badge-inline badge-approval", text: ap.approval_doc_no || "已准予行政许可" }),
                el("span", { className: "muted-line", text: ap.approval_source || "省文旅厅公示" })
              ),
              el("h3", { className: "poster-artist mt-xs", text: `${ap.artist_name} · ${ap.city}站` }),
              el("div", { text: `${ap.show_time} · ${ap.venue}` }),
              el("p", { className: "muted-line mt-xs", text: ap.notes || "" }),
              el(
                "div",
                { className: "flex-row-wrap mt-xs" },
                el(
                  "button",
                  {
                    type: "button",
                    className: isArtistFavorited(ap.artist_name)
                      ? "btn-fav-star-inline is-favorited"
                      : "btn-fav-star-inline",
                    onClick: () => toggleFavoriteArtist(ap.artist_name),
                  },
                  isArtistFavorited(ap.artist_name) ? "★ 已收藏蹲官宣" : "☆ 收藏蹲官宣"
                ),
                ap.ticket_url
                  ? el("a", { href: ap.ticket_url, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, "查看政务公示源 ↗")
                  : null
              )
            )
          )
        : el(
            "article",
            { className: "watchlist-empty-box" },
            el("strong", { text: "各省市文旅局审批公示请点击下方政务官网核验（本页不虚构未发布批文）" }),
            el("p", {
              className: "muted-line mt-xs",
              text: "在官网看到新过审的营业性演出许可公示后，可直接复制全文粘贴到下方「官宣文案实时解析工作台」，系统将自动提取许可文号并加入此处与日历。",
            })
          )
    );

    setChildren(
      portalRow,
      el("span", { className: "muted-line", text: "各省市文旅局审批公示直达：" }),
      siteState.culturePortals.map((pt) =>
        el("a", { href: pt.url, target: "_blank", rel: "noopener noreferrer", className: "tag-pill" }, `${pt.name} ↗`)
      )
    );
  }

  // ---------------- Section 6: Smart Parser Playground + Direct .ics & Turso Save ----------------

  function initPlayground() {
    const presetRow = document.getElementById("playground-preset-buttons");
    const textarea = document.getElementById("playground-textarea");
    const out = document.getElementById("playground-result-box");
    const runBtn = document.getElementById("btn-run-playground");
    const clearBtn = document.getElementById("btn-playground-clear");
    if (!presetRow || !textarea || !runBtn) return;

    textarea.value = "";
    if (out) {
      setChildren(
        out,
        el("strong", { text: "等待粘贴真实官宣文案" }),
        el("p", {
          className: "muted-line mt-xs",
          text: "请从大麦 / 猫眼 / 微博 / 省市文旅局官网复制任意真实演出公告粘贴至左侧，点击「立即解析场次与节点」即可自动提取时间、场馆、开票节点与 12306 高铁日历。（上方按钮为虚构格式测试模板，仅用于体验解析功能。）",
        })
      );
    }
    setChildren(
      presetRow,
      PLAYGROUND_SAMPLES.map((sp) =>
        el(
          "button",
          {
            type: "button",
            className: "tag-pill",
            onClick: () => {
              textarea.value = sp.text;
              executePlaygroundParse();
            },
          },
          sp.label
        )
      )
    );

    runBtn.addEventListener("click", executePlaygroundParse);
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        textarea.value = "";
        const prevHost = document.getElementById("playground-photo-preview");
        if (prevHost) {
          prevHost.hidden = true;
          setChildren(prevHost);
        }
        textarea.focus();
      });
    }

    const photoBtn = document.getElementById("btn-playground-photo");
    const photoInput = document.getElementById("playground-photo-input");
    const prevHost = document.getElementById("playground-photo-preview");
    if (photoBtn && photoInput) {
      photoBtn.addEventListener("click", () => photoInput.click());
      photoInput.addEventListener("change", () => {
        const file = photoInput.files && photoInput.files[0];
        photoInput.value = "";
        if (!file) return;
        const allowed = ["image/png", "image/jpeg", "image/webp"];
        if (file.type && !allowed.includes(file.type)) {
          showSiteToast("仅支持 PNG、JPG/JPEG 或 WEBP 格式海报图片", true);
          return;
        }
        if (file.size > 5 * 1024 * 1024) {
          showSiteToast("海报图片超过 5MB 上限，请压缩后再试", true);
          return;
        }
        const reader = new FileReader();
        reader.onload = async () => {
          const dataUrl = String(reader.result || "");
          photoBtn.disabled = true;
          photoBtn.textContent = "⏳ 正在识图解析…";
          try {
            const res = await apiPost("/api/public/parse-festival-photo", {
              mode: "announcement",
              filename: file.name || "poster.png",
              image_base64: dataUrl,
              home_city: siteState.homeCity,
              vision_api_key: siteState.sessionVisionApiKey || "",
            });
            if (prevHost) {
              prevHost.hidden = false;
              const imgNode = el("img", {
                src: res.preview_data_url || dataUrl,
                alt: "官宣海报安全预览",
                className: "festival-photo-preview-img",
                title: "点击展开/收起大图",
                onClick: () => imgNode.classList.toggle("is-expanded"),
              });
              setChildren(
                prevHost,
                el("div", {
                  className: "muted-line",
                  text:
                    res.ocr_mode === "local_rapidocr"
                      ? "✅ 已用本地免费中文 OCR (PP-OCRv6) 提取海报文字并填入上方文本框（点击图片可放大核对）"
                      : res.ocr_mode === "gemini_vision"
                        ? "✅ 已用 Gemini Vision 提取海报文字并填入上方文本框"
                        : res.warning || "海报已安全净化并生成预览",
                }),
                imgNode
              );
            }
            if (res.extracted_text) {
              textarea.value = res.extracted_text;
              await executePlaygroundParse();
              showSiteToast("海报识图并解析完成，可一键导出 .ics 日历！");
            } else {
              showSiteToast(res.warning || "海报已载入预览，未检测到可读文字", true);
            }
          } catch (err) {
            showSiteToast((err && err.message) || "海报识图失败，请稍后重试", true);
          } finally {
            photoBtn.disabled = false;
            photoBtn.textContent = "📷 上传海报/批文长图识图";
          }
        };
        reader.readAsDataURL(file);
      });
    }
  }

  async function saveParsedItemsToVault(items) {
    if (!siteState.authenticated) {
      window.location.href = "/";
      return;
    }
    let okCount = 0;
    for (const it of items) {
      try {
        await apiPost("/api/concerts/create", it);
        okCount += 1;
      } catch (_e) {
        // Continue saving remaining shows
      }
    }
    if (okCount > 0) {
      showSiteToast(`💾 已将 ${okCount} 场解析演出存入你的 Turso 云端追踪库！`);
    } else {
      showSiteToast("保存未成功，请前往个人工作台确认登录状态", true);
    }
  }

  async function executePlaygroundParse() {
    const textarea = document.getElementById("playground-textarea");
    const out = document.getElementById("playground-result-box");
    const runBtn = document.getElementById("btn-run-playground");
    if (!textarea || !out) return;

    const raw = textarea.value.trim();
    if (!raw) {
      showSiteToast("请先输入或点选一段演出文案", true);
      return;
    }
    if (runBtn) runBtn.disabled = true;
    setChildren(out, el("p", { className: "muted-line", text: "正在调用解析引擎提取城市、场馆、抢票节点、周末预算与避坑指南..." }));

    try {
      const res = await apiPost("/api/public/parse-preview", {
        text: raw,
        home_city: siteState.homeCity,
      });
      const items = res.items || [];
      siteState.lastParsedItems = items;
      siteState.lastParsedRawText = raw;

      setChildren(
        out,
        el("div", { className: "rec-highlight", text: res.summary || `共解析出 ${items.length} 场演出` }),
        items.map((it, idx) =>
          el(
            "div",
            { className: "parsed-result-item" },
            el("strong", { text: `${idx + 1}. ${it.artist_name || "待确认艺人"} — ${it.city}站（${it.show_time}）` }),
            el("div", { className: "muted-line", text: `标题：${it.title} | 场馆：${it.venue || "待公布"} | 平台：${it.platform} ${it.price_text || ""}` }),
            it.approval_doc_no ? el("div", { className: "mt-xs", text: `政务批文：${it.approval_doc_no}（${it.approval_source}）` }) : null,
            (it.ticket_rounds || []).map((r) =>
              el("div", { className: "mt-xs", text: `抢票节点：[${r.round_label}] ${r.sale_time}（${r.platform}）` })
            ),
            (it.refund_tiers || []).map((rf) =>
              el("div", { className: "mt-xs muted-line", text: `退票/回流：[${rf.tier_label}] ${rf.cutoff_time}（费率 ${rf.fee_percent}%）` })
            ),
            it.rail_plan && it.rail_plan.is_cross_city
              ? el("div", {
                  className: "mt-xs muted-line",
                  text: `🚄 12306 高铁（${it.rail_plan.home_city}出发）：去程 ${formatRailSaleStatus(it.rail_plan.outbound_12306_sale_time)}`,
                })
              : null,
            it.trip_estimate
              ? el("div", {
                  className: "mt-xs muted-line",
                  text: `💰 周末观演参考总计：¥${it.trip_estimate.total_weekend_yuan}（${it.trip_estimate.transport_note}）`,
                })
              : null,
            it.venue_guide
              ? el("div", { className: "mt-xs muted-line", text: `🎯 选座攻略：${it.venue_guide.best_seats}` })
              : null
          )
        ),
        items.length > 0
          ? el(
              "div",
              { className: "mt-sm flex-row-wrap" },
              el(
                "button",
                {
                  type: "button",
                  className: "site-btn site-btn-sm",
                  onClick: async () => {
                    try {
                      await downloadParsedIcs(raw);
                      showSiteToast("已生成并下载本次解析演出的 .ics 日历闹钟！");
                    } catch (e) {
                      showSiteToast(e.message, true);
                    }
                  },
                },
                "↓ 导出本次解析日历 (.ics)"
              ),
              el(
                "button",
                {
                  type: "button",
                  className: "site-btn site-btn-sm",
                  onClick: () => {
                    const added = mergeConcertsIntoPage(items, items[0] && items[0].artist_name);
                    if (items[0] && items[0].artist_name) {
                      siteState.favoriteArtists.add(items[0].artist_name);
                      syncStateToUrl();
                    }
                    renderHeroKpiStrip();
                    renderWatchlistSection();
                    renderDropsSection();
                    renderDirectorySection();
                    const parsedFest = items.find((it) => it && it.event_kind === "festival");
                    if (parsedFest && parsedFest.id) {
                      siteState.selectedFestivalKey = `fest-${parsedFest.id}`;
                    }
                    renderFestivalSection();
                    showSiteToast(added > 0 ? `已将 ${added} 场解析演出加入本页排期、月历、地图与音乐节决策器！` : "该演出已存在于当前排期表中");
                  },
                },
                "＋ 加入本页地图/月历试看"
              ),
              siteState.authenticated
                ? el(
                    "button",
                    {
                      type: "button",
                      className: "site-btn site-btn-sm site-btn-primary",
                      onClick: () => saveParsedItemsToVault(items),
                    },
                    `💾 一键存入 Turso 追踪库 (${siteState.username})`
                  )
                : el("a", { href: "/", className: "site-btn site-btn-sm site-btn-primary" }, "登录并存入个人追踪库 →")
            )
          : null
      );
    } catch (err) {
      setChildren(out, el("p", { className: "muted-line", text: `解析失败：${err.message}` }));
    } finally {
      if (runBtn) runBtn.disabled = false;
    }
  }

  // ---------------- Section 7: Collectible Stub Museum & Custom PNG Studio ----------------

  function renderStubMuseum() {
    const grid = document.getElementById("stub-museum-grid");
    if (!grid) return;
    if (!siteState.archiveStubs.length) {
      setChildren(
        grid,
        el(
          "div",
          { className: "watchlist-empty-box" },
          el("strong", { text: "暂未添加你的真实观演票根" }),
          el("p", {
            className: "muted-line mt-xs",
            text: "本栏不预置虚构观演记录。点击右上角「＋ 制作我的纪念票根 PNG」，录入你真实看过的场次即可生成高清纪念票根卡片。",
          })
        )
      );
      return;
    }
    setChildren(
      grid,
      siteState.archiveStubs.map((st, idx) =>
        el(
          "article",
          { className: "museum-stub" },
          el(
            "div",
            null,
            el(
              "div",
              { className: "flex-row-between" },
              el("span", { className: "tour-date-col", text: `${st.city} · ${st.date}` }),
              el("span", { className: "stamp-verified", text: "已核验入场 · 纪念票根" })
            ),
            el("h3", { className: "poster-artist mt-xs", text: st.artist }),
            el("div", { className: "muted-line", text: st.title }),
            el("div", { className: "mt-xs", text: `实付 ¥${st.paid} · ${st.seat} · 视听评分 ${"★".repeat(st.rating || 5)}` }),
            el("div", { className: "stub-quote", text: `声场与选座参考：${st.acoustics}` }),
            el("div", { className: "stub-quote", text: `现场安可记忆：${st.memory}` })
          ),
          el(
            "div",
            { className: "stub-card-foot" },
            el("span", { className: "muted-line", text: `NO.${String(idx + 1).padStart(3, "0")}` }),
            el(
              "button",
              {
                type: "button",
                className: "site-btn site-btn-sm",
                onClick: () => {
                  const dataUrl = renderStubCanvasDataUrl(st);
                  openPngPreviewModal(`${st.artist} · 纪念票根高清预览 (PNG)`, dataUrl, `liveecho-stub-${st.city}-${st.date}.png`);
                },
              },
              "↓ 导出高清票根 PNG"
            )
          )
        )
      )
    );
  }

  function initStubCreator() {
    const toggleBtn = document.getElementById("btn-toggle-stub-creator");
    const cancelBtn = document.getElementById("btn-cancel-stub-creator");
    const form = document.getElementById("custom-stub-form");
    const dateInput = document.getElementById("stub-in-date");
    if (dateInput && !dateInput.value) {
      dateInput.value = nowShanghai.toISOString().slice(0, 10);
    }
    if (toggleBtn && form) {
      toggleBtn.addEventListener("click", () => {
        form.hidden = !form.hidden;
        if (!form.hidden) {
          const inp = document.getElementById("stub-in-artist");
          if (inp) inp.focus();
        }
      });
    }
    if (cancelBtn && form) {
      cancelBtn.addEventListener("click", () => {
        form.hidden = true;
      });
    }
    if (form) {
      form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const artist = (document.getElementById("stub-in-artist").value || "").trim();
        const city = (document.getElementById("stub-in-city").value || "").trim();
        const date = (document.getElementById("stub-in-date").value || "").trim();
        const venue = (document.getElementById("stub-in-venue").value || "").trim() || "现场场馆";
        const seat = (document.getElementById("stub-in-seat").value || "").trim() || "现场观演位";
        const paid = Number(document.getElementById("stub-in-paid").value) || 580;
        const acoustics = (document.getElementById("stub-in-acoustics").value || "").trim() || "现场声像清晰饱满，体验绝佳。";
        const memory = (document.getElementById("stub-in-memory").value || "").trim() || "又一场值得珍藏的现场回响。";
        if (!artist || !city || !date) {
          showSiteToast("请填写艺人、城市与演出日期", true);
          return;
        }
        const newStub = {
          city,
          date,
          artist,
          venue,
          title: `${artist} ${city}专场 @ ${venue}`,
          paid,
          seat,
          rating: 5,
          acoustics,
          memory,
        };
        siteState.archiveStubs.unshift(newStub);
        persistSavedStubs();
        renderStubMuseum();
        form.hidden = true;
        form.reset();
        if (dateInput) dateInput.value = nowShanghai.toISOString().slice(0, 10);
        const dataUrl = renderStubCanvasDataUrl(newStub);
        openPngPreviewModal(`${artist} · 你的专属纪念票根 (PNG)`, dataUrl, `liveecho-stub-${city}-${date}.png`);
        showSiteToast(`已为「${artist} · ${city}站」生成专属纪念票根！`);
      });
    }
  }

  // ---------------- Scroll-Spy, Mobile Drawer, Floating Dock & Ticker ----------------

  function initNavigationPolish() {
    const mobileToggle = document.getElementById("btn-mobile-nav-toggle");
    const navBar = document.getElementById("site-nav-bar");
    if (mobileToggle && navBar) {
      mobileToggle.addEventListener("click", () => {
        const open = navBar.classList.toggle("is-open");
        mobileToggle.setAttribute("aria-expanded", open ? "true" : "false");
        mobileToggle.textContent = open ? "✕ 收起" : "☰ 菜单";
      });
      navBar.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
          navBar.classList.remove("is-open");
          mobileToggle.setAttribute("aria-expanded", "false");
          mobileToggle.textContent = "☰ 菜单";
        });
      });
    }

    // Active section scroll-spy
    const sectionIds = ["watchlist", "drops", "directory", "festivals", "approvals", "playground", "archive"];
    if ("IntersectionObserver" in window) {
      const obs = new IntersectionObserver(
        (entries) => {
          for (const ent of entries) {
            if (!ent.isIntersecting) continue;
            const id = ent.target.id;
            document.querySelectorAll(".site-nav a").forEach((a) => {
              a.classList.toggle("is-active", a.getAttribute("href") === `#${id}`);
            });
          }
        },
        { rootMargin: "-25% 0px -65% 0px" }
      );
      for (const id of sectionIds) {
        const sec = document.getElementById(id);
        if (sec) obs.observe(sec);
      }
    }

    // Floating quick-jump dock
    const dock = document.getElementById("floating-dock");
    const topBtn = document.getElementById("dock-top-btn");
    if (topBtn) {
      topBtn.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    }
    if (dock) {
      const updateDock = () => {
        dock.hidden = window.scrollY < 420;
      };
      window.addEventListener("scroll", updateDock, { passive: true });
      updateDock();
    }

    // Modal dismiss & global keyboard shortcuts ("/" to search, "Esc" to close modal/nav)
    const modalClose = document.getElementById("site-modal-close");
    const modalOverlay = document.getElementById("site-modal-overlay");
    if (modalClose) modalClose.addEventListener("click", closeSiteModal);
    if (modalOverlay) {
      modalOverlay.addEventListener("click", (ev) => {
        if (ev.target === modalOverlay) closeSiteModal();
      });
    }
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        closeSiteModal();
        if (navBar) navBar.classList.remove("is-open");
      } else if (ev.key === "/" && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
        const tag = (document.activeElement && document.activeElement.tagName) || "";
        if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
          ev.preventDefault();
          const inp = document.getElementById("hero-artist-input");
          if (inp) {
            inp.focus();
            inp.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        }
      }
    });
  }

  function startWebsiteTicker() {
    let checkCounter = 0;
    const tick = () => {
      const clock = document.getElementById("site-beijing-clock");
      if (clock) clock.textContent = formatClockNow();
      const nowMs = Date.now();
      document.querySelectorAll("[data-site-countdown]").forEach((node) => {
        const ms = Number(node.getAttribute("data-site-countdown"));
        if (ms) node.textContent = formatCountdown(ms, nowMs);
      });

      checkCounter += 1;
      if (siteState.browserAlertsEnabled && checkCounter % 15 === 0) {
        const favAlerts = collectPresalesForArtists(Array.from(siteState.favoriteArtists));
        const leads = Array.from(new Set([siteState.alertLeadMinutes, 5, 1]));
        for (const al of favAlerts) {
          if (!al.ms) continue;
          const diffMin = (al.ms - nowMs) / 60000;
          for (const lead of leads) {
            if (diffMin > 0 && diffMin <= lead && diffMin >= lead - 0.6) {
              const fk = `${al.key}:m${lead}`;
              if (siteState.firedAlertKeys.has(fk)) continue;
              siteState.firedAlertKeys.add(fk);
              const msg = `【即将预售提醒】${al.artist} ${al.city}站（${al.presaleLabel}）将在约 ${Math.max(1, Math.round(diffMin))} 分钟后于 ${al.platform} 开抢！`;
              showSiteToast(msg);
              try {
                if ("Notification" in window && Notification.permission === "granted") {
                  new Notification(`现场回响 · ${al.artist} ${al.city}站即将预售`, { body: msg });
                }
              } catch (_e) {
                // Ignore Notification errors
              }
            }
          }
        }
      }
    };
    tick();
    window.setInterval(tick, 1000);
  }

  async function initWebsite() {
    applyTheme(siteState.theme);
    const originSel = document.getElementById("site-home-city-select");
    if (originSel) originSel.value = siteState.homeCity;

    const themeBtn = document.getElementById("btn-theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        applyTheme(siteState.theme === "dark" ? "light" : "dark");
        showSiteToast(siteState.theme === "dark" ? "已切换至「黑胶暗夜」主题" : "已切换至「宣纸日光」主题");
      });
    }

    initNavigationPolish();
    initStubCreator();
    renderHeroQuickArtists();
    renderStubMuseum();
    startWebsiteTicker();

    const searchForm = document.getElementById("hero-artist-search-form");
    if (searchForm) {
      searchForm.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const inp = document.getElementById("hero-artist-input");
        if (inp && inp.value.trim()) runHeroArtistSearch(inp.value.trim());
      });
    }

    if (originSel) {
      originSel.addEventListener("change", async () => {
        siteState.homeCity = originSel.value;
        safeWritePref("liveecho_home_city", siteState.homeCity);
        syncStateToUrl();
        await loadShowcaseData();
        showSiteToast(`已切换出发地为「${siteState.homeCity}」，高铁日历、巡演地图与周末预算已同步更新`);
      });
    }

    const dirFilter = document.getElementById("directory-filter-input");
    if (dirFilter) {
      dirFilter.addEventListener("input", () => {
        siteState.directoryQuery = dirFilter.value;
        renderDirectorySection();
      });
    }

    const refreshBtn = document.getElementById("btn-refresh-live-feed");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", async () => {
        refreshBtn.disabled = true;
        refreshBtn.textContent = "↻ 正在同步...";
        try {
          await loadShowcaseData(true);
          showSiteToast(`已从秀动 ShowStart 重新同步最新实时排期（${siteState.liveFetchedAt || "刚刚"}）`);
        } catch (_e) {
          showSiteToast("刷新实时数据失败，请稍后再试", true);
        } finally {
          refreshBtn.disabled = false;
          refreshBtn.textContent = "↻ 刷新实时排期";
        }
      });
    }

    try {
      await loadShowcaseData(false);
      initPlayground();
    } catch (_err) {
      showSiteToast("加载演出门户数据失败，请刷新重试", true);
    }

    // Support Ctrl+V / Cmd+V screenshot paste when a real festival is selected in STEP 01
    document.addEventListener("paste", (ev) => {
      if (!siteState.selectedFestivalKey || siteState.selectedFestivalKey === "demo-simulator") return;
      if (typeof siteState._activeFestivalPhotoDropHandler !== "function") return;
      const items = (ev.clipboardData && ev.clipboardData.items) || [];
      for (const it of items) {
        if (it.type && it.type.startsWith("image/")) {
          const f = it.getAsFile();
          if (f) {
            ev.preventDefault();
            siteState._activeFestivalPhotoDropHandler(f);
            break;
          }
        }
      }
    });

    // Visibility-aware refresh: zero background pings while tab is hidden (lets Render Free Tier sleep cleanly!),
    // automatically refreshes when the user returns to the tab and data is older than 15 minutes.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) return;
      const ageMs = Date.now() - (siteState.lastShowcaseLoadMs || 0);
      if (ageMs >= 15 * 60 * 1000) {
        loadShowcaseData(false).catch(() => {});
      }
    });
  }

  document.addEventListener("DOMContentLoaded", initWebsite);
})();
