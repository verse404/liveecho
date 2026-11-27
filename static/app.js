/* LiveEcho (现场回响) v2 — Full China Concert Suite Frontend.
 * Strictly XSS-safe & CSP-safe: zero innerHTML/outerHTML, zero inline style attributes,
 * zero localStorage tokens, zero native alert/confirm/prompt.
 */
(function () {
  "use strict";

  const STATUS_LABELS = {
    approved_pending: "已过审·待官宣",
    upcoming_drop: "待抢票",
    announced: "已官宣·待定开票",
    waiting_round2: "蹲二开/回流票",
    purchased: "已购票·待观演",
    discovered: "雷达新发现",
    attended: "已观演·票根归档",
  };

  const PLATFORMS = ["大麦", "猫眼", "秀动", "B站会员购", "纷玩岛", "摩天轮", "票星球", "文旅局公示"];

  const SAMPLE_SINGLE_WITH_REFUND = [
    "【官宣】草东没有派对 2026 专场演出（杭州站）",
    "演出时间：2026年12月19日 19:30",
    "演出场馆：杭州奥体中心体育馆",
    "票价：¥380 / 580 / 780 / 980元",
    "优先购开启：2026年11月22日 11:18（纷玩岛）",
    "正式开票时间：2026年11月23日 12:18（大麦）",
    "退票规则：开票后48小时内无条件退票（0%手续费）",
    "退票规则：2026年12月05日 12:00前退票收取20%手续费",
    "2026年12月15日 12:00停止退票",
    "https://www.damai.cn/",
  ].join("\n");

  const SAMPLE_TOUR_MULTI = [
    "#新裤子乐队北海怪兽巡回演唱会# 正式官宣三城排期！",
    "票价：¥380-1080",
    "抢票时间：2026年11月25日 12:18 大麦同步开售",
    "开票后48小时内无条件退票",
    "2026年12月12日 19:30 上海 浦发银行东方体育中心",
    "2026年12月26日 19:30 广州 宝能广州国际体育演艺中心",
    "2027年01月09日 19:30 武汉 光谷国际网球中心",
    "https://www.damai.cn/",
  ].join("\n");

  const SAMPLE_APPROVAL_FILING = [
    "广东省文化和旅游厅关于准予举办陈奕迅2027巡回演唱会（深圳站）的行政许可决定",
    "许可文号：粤文旅审〔2026〕1928号",
    "举办日期：2027年01月16日 19:30",
    "演出场所：深圳大运中心体育场",
    "申请演出演员：陈奕迅",
    "https://dct.gd.gov.cn/",
  ].join("\n");

  const SAMPLE_FESTIVAL_TIMETABLE = [
    "2026广州超级草莓音乐节 全阵容时刻表公布！",
    "演出时间：2026年12月05日 13:30",
    "地点：[广州]南沙音乐秀场",
    "票价：¥368-658",
    "正式开票：2026年11月21日 11:18（秀动）",
    "2026年12月05日",
    "草莓舞台 19:30-20:15 新裤子",
    "爱舞台 19:50-20:35 落日飞车",
    "2026年12月06日",
    "草莓舞台 20:10-20:55 万能青年旅店",
    "https://www.showstart.com/",
  ].join("\n");

  const state = {
    authenticated: false,
    needsSetup: false,
    csrfToken: "",
    user: null,
    regions: {},
    culturePortals: [],
    presets: [],
    artists: [],
    concerts: [],
    festivalGroups: [],
    stubStats: {},
    notifSettings: null,

    activeTab: "all", // all | drops | approvals | festivals | purchased | stubs | artists | discovered
    selectedRegion: "all",
    selectedCity: "all",
    searchQuery: "",
    sortMode: "show_asc", // show_asc | action_asc
    firedBrowserAlerts: new Set(),
    clockTimerId: null,
    activePasteHandler: null,
    lastFocusedElement: null,
  };

  // ---------------- Safe DOM Builders ----------------

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

  function setChildren(parent, ...items) {
    if (!parent) return;
    const flatNodes = items
      .flat(Infinity)
      .filter((x) => x !== null && x !== undefined && x !== false)
      .map((x) => (typeof x === "string" || typeof x === "number" ? document.createTextNode(String(x)) : x));
    parent.replaceChildren(...flatNodes);
  }

  function showToast(message, isError) {
    const root = document.getElementById("toast-root");
    if (!root) return;
    const item = el("div", {
      className: isError ? "toast-item error" : "toast-item",
      text: message,
    });
    root.appendChild(item);
    window.setTimeout(() => {
      if (item.parentNode) item.parentNode.removeChild(item);
    }, 4000);
  }

  function closeModal() {
    if (state.activePasteHandler) {
      document.removeEventListener("paste", state.activePasteHandler);
      state.activePasteHandler = null;
    }
    const root = document.getElementById("modal-root");
    if (root) root.replaceChildren();
    if (state.lastFocusedElement && typeof state.lastFocusedElement.focus === "function") {
      try {
        state.lastFocusedElement.focus();
      } catch (_e) {
        // Element may have re-rendered
      }
      state.lastFocusedElement = null;
    }
  }

  function openModal(titleText, bodyNode) {
    const prevFocus = document.activeElement;
    closeModal();
    state.lastFocusedElement = prevFocus;
    const root = document.getElementById("modal-root");
    if (!root) return;
    const closeBtn = el(
      "button",
      {
        type: "button",
        id: "modal-close-btn",
        className: "btn btn-sm",
        onClick: closeModal,
      },
      "关闭"
    );
    const panel = el(
      "div",
      {
        className: "modal-panel",
        role: "dialog",
        "aria-modal": "true",
        "aria-labelledby": "modal-dialog-title",
        onClick: (ev) => ev.stopPropagation(),
      },
      el("div", { className: "modal-head" }, el("h2", { id: "modal-dialog-title", text: titleText }), closeBtn),
      bodyNode
    );
    const backdrop = el("div", { className: "modal-backdrop", onClick: closeModal }, panel);
    root.replaceChildren(backdrop);
    window.requestAnimationFrame(() => {
      const firstFocusable = panel.querySelector("input:not(.hidden-input), textarea, select, button");
      if (firstFocusable && typeof firstFocusable.focus === "function") {
        firstFocusable.focus();
      }
    });
  }

  function openConfirmDialog(titleText, messageText, confirmLabel, onConfirm) {
    const actions = el(
      "div",
      { className: "modal-actions" },
      el("button", { type: "button", className: "btn", onClick: closeModal }, "取消"),
      el(
        "button",
        {
          type: "button",
          className: "btn btn-primary",
          onClick: async () => {
            closeModal();
            await onConfirm();
          },
        },
        confirmLabel || "确认"
      )
    );
    openModal(titleText, el("div", null, el("p", { text: messageText }), actions));
  }

  // ---------------- Time & Shanghai UTC+8 Helpers ----------------

  function parseShanghaiEpochMs(dtStr) {
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

  function formatShanghaiNow() {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date());
  }

  function formatCountdownText(targetMs, nowMs) {
    const diffSec = Math.floor((targetMs - nowMs) / 1000);
    if (diffSec <= -1800) return "窗口已过";
    if (diffSec <= 0) return "正在开抢/回流！";
    const days = Math.floor(diffSec / 86400);
    const hours = Math.floor((diffSec % 86400) / 3600);
    const mins = Math.floor((diffSec % 3600) / 60);
    const secs = diffSec % 60;
    const hh = String(hours).padStart(2, "0");
    const mm = String(mins).padStart(2, "0");
    const ss = String(secs).padStart(2, "0");
    return days > 0 ? `${days}天 ${hh}:${mm}:${ss}` : `${hh}:${mm}:${ss}`;
  }

  // ---------------- API Client ----------------

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
        "X-CSRF-Token": state.csrfToken,
      },
      body: JSON.stringify(payload || {}),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.status === 403 && !_retried && (path === "/api/auth/register" || path === "/api/auth/login")) {
      try {
        const freshAuth = await apiGet("/api/auth/status");
        if (freshAuth.csrf_token) {
          state.csrfToken = freshAuth.csrf_token;
          return apiPost(path, payload, true);
        }
      } catch (_refreshErr) {
        // Fall through to standard error below
      }
    }
    if (resp.status === 401 && state.authenticated && path !== "/api/auth/login") {
      state.authenticated = false;
      state.csrfToken = "";
      closeModal();
      const freshAuth = await apiGet("/api/auth/status").catch(() => ({}));
      state.csrfToken = freshAuth.csrf_token || "";
      renderAuthScreen("login");
      throw new Error("登录会话已过期，请重新登录。");
    }
    if (!resp.ok) throw new Error(data.error || `请求失败 (${resp.status})`);
    return data;
  }

  // ---------------- Bootstrap & Session Lifecycle ----------------

  async function initApp() {
    try {
      const auth = await apiGet("/api/auth/status");
      state.csrfToken = auth.csrf_token || "";
      state.authenticated = Boolean(auth.authenticated);
      state.needsSetup = Boolean(auth.needs_setup);
      state.presets = auth.presets || [];
      state.regions = auth.regions || {};

      if (state.authenticated) {
        await refreshWorkspace();
      } else {
        renderAuthScreen(state.needsSetup ? "register" : "login");
      }
      startLiveTicker();
    } catch (_err) {
      showToast("初始化连接失败，请刷新页面重试", true);
    }
  }

  async function refreshWorkspace() {
    const boot = await apiGet("/api/bootstrap");
    state.csrfToken = boot.csrf_token || state.csrfToken;
    state.user = boot.user;
    state.regions = boot.regions || {};
    state.culturePortals = boot.culture_portals || [];
    state.presets = boot.presets || [];
    state.artists = boot.artists || [];
    state.concerts = boot.concerts || [];
    state.festivalGroups = boot.festival_groups || [];
    state.stubStats = boot.stub_wall_stats || {};
    state.notifSettings = boot.notification_settings || {};
    renderWorkspace();
  }

  async function handleLogout() {
    try {
      await apiPost("/api/auth/logout", {});
    } catch (_e) {
      // Proceed with clean local state wipe
    }
    state.authenticated = false;
    state.csrfToken = "";
    state.user = null;
    state.artists = [];
    state.concerts = [];
    window.location.href = "/";
  }

  // ---------------- Onboarding / Login Screen ----------------

  function renderAuthScreen(mode) {
    const root = document.getElementById("app-root");
    if (!root) return;

    const isRegister = mode === "register";
    const selectedStarters = new Set(["万能青年旅店", "落日飞车", "草东没有派对", "痛仰乐队", "陶喆", "新裤子"]);

    const usernameInput = el("input", {
      id: "auth-username",
      type: "text",
      autocomplete: "username",
      placeholder: "例如：echo_fan",
      required: true,
    });
    const passwordInput = el("input", {
      id: "auth-password",
      type: "password",
      autocomplete: isRegister ? "new-password" : "current-password",
      placeholder: isRegister ? "至少 8 位字符（推荐 12 位以上）" : "输入密码",
      required: true,
    });
    const homeCityInput = el("input", {
      id: "auth-home-city",
      type: "text",
      value: "上海",
      placeholder: "如：上海 / 北京 / 深圳（用于自动计算跨城 12306 高铁开售日）",
    });
    const regionSelect = el(
      "select",
      { id: "auth-region" },
      Object.entries(
        state.regions.all
          ? state.regions
          : { all: "全国全部", jzh: "江浙沪皖", jjj: "京津冀", gba: "广深港澳", cy: "川渝西南" }
      ).map(([code, label]) => el("option", { value: code, text: label }))
    );
    const demoCheckbox = el("input", { id: "auth-demo-seed", type: "checkbox", checked: false });
    const customArtistObjects = new Map();

    const starterContainer = el("div", { className: "preset-picker" });
    const customSearchHint = el("div", { className: "hint-text" });
    const customArtistIn = el("input", {
      id: "auth-custom-artist-input",
      type: "text",
      placeholder: "自己输入任意歌手/乐队（如：陈粒 / 毛不易 / 孙燕姿 / 房东的猫）",
    });
    const customArtistBtn = el(
      "button",
      {
        id: "auth-custom-artist-btn",
        type: "button",
        className: "btn btn-sm",
        onClick: async () => {
          const rawName = customArtistIn.value.trim();
          if (!rawName) return;
          customArtistBtn.disabled = true;
          customSearchHint.textContent = `正在联网检索「${rawName}」及近期中国演出...`;
          try {
            const bundle = await apiGet(`/api/public/artist-preview?q=${encodeURIComponent(rawName)}`);
            const prof = bundle.primary_profile || { name: rawName, genre: "", aliases: [] };
            const concertsFound = bundle.concerts || [];
            customArtistObjects.set(prof.name, {
              ...prof,
              discovered_concerts: concertsFound,
            });
            selectedStarters.add(prof.name);
            const chip = el(
              "button",
              {
                type: "button",
                className: "chip selected",
                onClick: () => {
                  if (selectedStarters.has(prof.name)) {
                    selectedStarters.delete(prof.name);
                    customArtistObjects.delete(prof.name);
                    chip.className = "chip";
                  } else {
                    selectedStarters.add(prof.name);
                    customArtistObjects.set(prof.name, { ...prof, discovered_concerts: concertsFound });
                    chip.className = "chip selected";
                  }
                },
              },
              concertsFound.length > 0 ? `${prof.name}（搜到${concertsFound.length}场）` : prof.name
            );
            starterContainer.prepend(chip);
            customArtistIn.value = "";
            customSearchHint.textContent =
              concertsFound.length > 0
                ? `已识别「${prof.name}」（${prof.genre || "音乐人"}），并自动搜到 ${concertsFound.length} 场近期演出！注册后将自动导入。`
                : `已识别并添加「${prof.name}」（${prof.genre || "音乐人"}），进入后可随时自动扫描巡演雷达。`;
          } catch (err) {
            customSearchHint.textContent = "";
            showToast(err.message, true);
          } finally {
            customArtistBtn.disabled = false;
          }
        },
      },
      "搜索并添加"
    );
    customArtistIn.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        customArtistBtn.click();
      }
    });

    if (isRegister) {
      for (const p of state.presets) {
        const chip = el(
          "button",
          {
            type: "button",
            className: selectedStarters.has(p.name) ? "chip selected" : "chip",
            onClick: () => {
              if (selectedStarters.has(p.name)) {
                selectedStarters.delete(p.name);
                chip.className = "chip";
              } else {
                selectedStarters.add(p.name);
                chip.className = "chip selected";
              }
            },
          },
          p.name
        );
        starterContainer.appendChild(chip);
      }
    }

    const submitBtn = el(
      "button",
      {
        id: "auth-submit-btn",
        type: "submit",
        className: "btn btn-primary btn-block",
      },
      isRegister ? "创建追踪库并进入" : "登录现场回响"
    );

    const form = el(
      "form",
      {
        onSubmit: async (ev) => {
          ev.preventDefault();
          submitBtn.disabled = true;
          try {
            if (isRegister) {
              const res = await apiPost("/api/auth/register", {
                username: usernameInput.value.trim(),
                password: passwordInput.value,
                preferred_region: regionSelect.value,
                home_city: homeCityInput.value.trim() || "上海",
                starter_artists: Array.from(selectedStarters),
                custom_artist_objects: Array.from(customArtistObjects.values()),
                include_demo_concerts: demoCheckbox.checked,
              });
              state.csrfToken = res.csrf_token;
              state.authenticated = true;
              showToast("欢迎来到现场回响 v2！全功能追踪库已就绪");
              await refreshWorkspace();
            } else {
              const res = await apiPost("/api/auth/login", {
                username: usernameInput.value.trim(),
                password: passwordInput.value,
              });
              state.csrfToken = res.csrf_token;
              state.authenticated = true;
              await refreshWorkspace();
            }
          } catch (err) {
            showToast(err.message, true);
          } finally {
            submitBtn.disabled = false;
          }
        },
      },
      el("div", { className: "form-field" }, el("label", { for: "auth-username", text: "账户名称" }), usernameInput),
      el("div", { className: "form-field" }, el("label", { for: "auth-password", text: "访问密码" }), passwordInput),
      isRegister
        ? el(
            "div",
            null,
            el(
              "div",
              { className: "form-grid" },
              el("div", { className: "form-field" }, el("label", { for: "auth-home-city", text: "常驻出发城市（计算 12306 高铁提醒）" }), homeCityInput),
              el("div", { className: "form-field" }, el("label", { for: "auth-region", text: "默认浏览区域" }), regionSelect)
            ),
            el(
              "div",
              { className: "form-field" },
              el("label", { for: "auth-custom-artist-input", text: "自己输入或点选喜爱的歌手与乐队（系统自动检索档案与近期演出）" }),
              el("div", { className: "row-gap mb-sm" }, customArtistIn, customArtistBtn),
              customSearchHint,
              starterContainer
            ),
            el(
              "label",
              { className: "demo-opt-label" },
              demoCheckbox,
              "预置 5 场全功能演示排期（含抢票/退票回流、文旅过审、音乐节撞场、12306高铁与纪念票根）"
            )
          )
        : null,
      submitBtn
    );

    root.replaceChildren(
      el(
        "main",
        { className: "auth-wrapper" },
        el("div", { className: "brand-mark" }, el("span", { className: "stamp-seal", text: "回响" }), el("strong", { text: "LiveEcho · 现场回响 v2" })),
        el("h1", { text: isRegister ? "不错过任何一场心仪现场" : "登录你的演出追踪库" }),
        el(
          "p",
          {
            className: "auth-subtitle",
            text: "集齐中国观演六大刚需：官宣文案与长图海报识图、省文旅局审批早鸟、音乐节单日票与撞场预警、阶梯退票与回流狙击、跨城 12306 高铁联动、观演票根纪念墙。",
          }
        ),
        form,
        el(
          "div",
          { className: "row-between mt-md" },
          el(
            "button",
            {
              type: "button",
              className: "btn btn-quiet btn-sm",
              onClick: () => renderAuthScreen(isRegister ? "login" : "register"),
            },
            isRegister ? "已有账号？前往登录" : "创建新账号"
          ),
          el(
            "a",
            { href: "/website", className: "btn btn-sm" },
            "免登录浏览官网门户版 →"
          )
        )
      )
    );
  }

  // ---------------- Imminent Drops & Returned-Ticket Snipers ----------------

  function getImminentMilestones() {
    const nowMs = Date.now();
    const milestones = [];

    for (const c of state.concerts) {
      if (c.status === "attended" || c.status === "discovered") continue;
      if (state.selectedRegion !== "all" && c.region !== state.selectedRegion) continue;

      if (c.status !== "purchased") {
        for (const r of c.ticket_rounds || []) {
          const ms = parseShanghaiEpochMs(r.sale_time);
          if (ms && ms > nowMs - 15 * 60 * 1000) {
            milestones.push({
              kind: "drop",
              concert: c,
              label: `抢票 · ${r.round_label}（${r.platform || c.platform}）`,
              timeStr: r.sale_time,
              url: r.booking_url || c.ticket_url,
              targetMs: ms,
            });
          }
        }
        for (const rf of c.refund_tiers || []) {
          if (!rf.expect_return_drop) continue;
          const ms = parseShanghaiEpochMs(rf.cutoff_time);
          if (ms && ms > nowMs - 15 * 60 * 1000) {
            milestones.push({
              kind: "sniper",
              concert: c,
              label: `回流狙击 · ${rf.tier_label}`,
              timeStr: rf.cutoff_time,
              url: c.ticket_url,
              targetMs: ms,
            });
          }
        }
      }
    }
    milestones.sort((a, b) => a.targetMs - b.targetMs);
    return milestones.slice(0, 4);
  }

  function getNextActionEpochMs(c, nowMs) {
    let earliest = Infinity;
    for (const r of c.ticket_rounds || []) {
      const ms = parseShanghaiEpochMs(r.sale_time);
      if (ms && ms > nowMs - 15 * 60 * 1000 && ms < earliest) earliest = ms;
    }
    for (const rf of c.refund_tiers || []) {
      if (!rf.expect_return_drop && c.status !== "purchased") continue;
      const ms = parseShanghaiEpochMs(rf.cutoff_time);
      if (ms && ms > nowMs - 15 * 60 * 1000 && ms < earliest) earliest = ms;
    }
    return earliest;
  }

  function getFilteredConcerts() {
    const q = state.searchQuery.trim().toLowerCase();
    const nowMs = Date.now();
    const list = state.concerts.filter((c) => {
      if (state.activeTab === "discovered") {
        if (c.status !== "discovered") return false;
      } else if (state.activeTab === "stubs") {
        if (c.status !== "attended") return false;
      } else if (state.activeTab === "approvals") {
        if (c.status !== "approved_pending") return false;
      } else {
        if (c.status === "discovered" || c.status === "attended") return false;
        if (
          state.activeTab === "drops" &&
          c.status !== "upcoming_drop" &&
          c.status !== "waiting_round2"
        ) {
          return false;
        }
        if (state.activeTab === "purchased" && c.status !== "purchased") return false;
      }

      if (state.selectedRegion !== "all" && c.region !== state.selectedRegion) return false;
      if (state.selectedCity !== "all" && c.city !== state.selectedCity) return false;

      if (q) {
        const hay = `${c.artist_name} ${c.title} ${c.city} ${c.venue} ${c.platform} ${c.approval_doc_no || ""} ${c.notes || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    if (state.sortMode === "action_asc") {
      list.sort((a, b) => {
        const na = getNextActionEpochMs(a, nowMs);
        const nb = getNextActionEpochMs(b, nowMs);
        if (na !== nb) return na - nb;
        return String(a.show_time || "").localeCompare(String(b.show_time || ""));
      });
    }
    return list;
  }

  // ---------------- Main Workspace Renderer ----------------

  function renderWorkspace() {
    const root = document.getElementById("app-root");
    if (!root) return;

    const activeTracked = state.concerts.filter((c) => c.status !== "discovered" && c.status !== "attended");
    const dropCount = state.concerts.filter((c) => c.status === "upcoming_drop" || c.status === "waiting_round2").length;
    const approvalCount = state.concerts.filter((c) => c.status === "approved_pending").length;
    const festCount = state.festivalGroups.length;
    const purchasedCount = state.concerts.filter((c) => c.status === "purchased").length;
    const stubCount = state.concerts.filter((c) => c.status === "attended").length;
    const discoveredCount = state.concerts.filter((c) => c.status === "discovered").length;

    // 1. Masthead
    const masthead = el(
      "header",
      { className: "masthead" },
      el(
        "div",
        { className: "masthead-left" },
        el("span", { className: "stamp-seal", text: "回响" }),
        el(
          "div",
          null,
          el("h1", { className: "masthead-title", text: "现场回响 · 中国演唱会与抢票追踪" }),
          el(
            "div",
            { className: "masthead-caption" },
            el("span", { text: `${state.user.username} · 常驻出发地：${state.user.home_city || "上海"}` }),
            el(
              "button",
              {
                type: "button",
                className: "btn btn-quiet btn-sm",
                onClick: openHomeCityModal,
              },
              "修改出发城市"
            )
          )
        )
      ),
      el(
        "div",
        { className: "masthead-right" },
        el(
          "div",
          { className: "clock-box" },
          el("span", { text: "北京时间" }),
          el("span", { id: "beijing-clock", className: "clock-digits", text: formatShanghaiNow() })
        ),
        el(
          "button",
          {
            id: "btn-smart-add",
            type: "button",
            className: "btn btn-primary",
            onClick: () => openConcertModal(null, "paste"),
          },
          "+ 文案 / 海报识图 / 新增"
        ),
        el(
          "button",
          {
            id: "btn-poster-quick",
            type: "button",
            className: "btn",
            onClick: () => openConcertModal(null, "poster"),
          },
          "长图海报导入"
        ),
        el(
          "button",
          {
            id: "btn-run-radar",
            type: "button",
            className: "btn",
            onClick: handleRunDiscoveryRadar,
          },
          "巡演雷达扫描"
        ),
        el(
          "button",
          {
            id: "btn-open-reminders",
            type: "button",
            className: "btn",
            onClick: openReminderCenterModal,
          },
          "提醒与日历同步"
        ),
        el(
          "a",
          {
            id: "btn-open-website",
            href: "/website",
            className: "btn",
          },
          "官网门户版"
        ),
        el(
          "button",
          {
            id: "btn-logout",
            type: "button",
            className: "btn btn-quiet",
            onClick: handleLogout,
          },
          "退出"
        )
      )
    );

    // 2. Imminent Drops + Returned-Ticket Snipers Strip
    const milestones = getImminentMilestones();
    const showSpotlight =
      milestones.length > 0 && !["artists", "stubs", "festivals"].includes(state.activeTab);
    const spotlightSection = showSpotlight
      ? el(
          "section",
          { className: "drop-spotlight", "aria-label": "近期抢票与回流狙击台" },
          el(
            "div",
            { className: "section-head" },
            el("h2", { className: "section-title", text: "近期抢票冲刺 & 退票回流狙击台" }),
            el("span", { className: "hint-text", text: "绿色卡片为阶梯退票截止前的「回流余票」蹲守窗口" })
          ),
          el(
            "div",
            { className: "drop-strip-grid" },
            milestones.map((m) =>
              el(
                "div",
                { className: m.kind === "sniper" ? "drop-mini-card sniper-mode" : "drop-mini-card" },
                el(
                  "div",
                  { className: "drop-mini-top" },
                  el(
                    "div",
                    null,
                    el("div", { className: "drop-mini-artist", text: `${m.concert.artist_name} · ${m.concert.city}站` }),
                    el("div", { className: "drop-mini-meta", text: `${m.label} · ${m.timeStr}` })
                  ),
                  m.url
                    ? el(
                        "a",
                        {
                          href: m.url,
                          target: "_blank",
                          rel: "noopener noreferrer",
                          className: "btn btn-sm",
                        },
                        m.kind === "sniper" ? "蹲回流" : "去抢票"
                      )
                    : null
                ),
                el("div", {
                  className: "countdown-timer",
                  "data-countdown-ms": String(m.targetMs),
                  text: formatCountdownText(m.targetMs, Date.now()),
                })
              )
            )
          )
        )
      : null;

    // 3. Navigation Tabs
    const makeTab = (key, label, count, urgent) =>
      el(
        "button",
        {
          id: `tab-${key}`,
          type: "button",
          className: state.activeTab === key ? "tab-btn active" : "tab-btn",
          onClick: () => {
            state.activeTab = key;
            renderWorkspace();
          },
        },
        label,
        count !== null
          ? el("span", { className: urgent ? "count-pill urgent" : "count-pill", text: String(count) })
          : null
      );

    const availableCities = Array.from(
      new Set(
        state.concerts
          .filter((c) => state.selectedRegion === "all" || c.region === state.selectedRegion)
          .map((c) => c.city)
          .filter(Boolean)
      )
    );

    const showRegionFilters = !["artists", "festivals", "stubs"].includes(state.activeTab);

    const controlsBar = el(
      "nav",
      { className: "controls-bar" },
      el(
        "div",
        { className: "nav-tabs" },
        el(
          "div",
          { className: "tab-group" },
          makeTab("all", "全部排期", activeTracked.length, false),
          makeTab("drops", "待抢票/回流", dropCount, dropCount > 0),
          makeTab("approvals", "文旅过审早鸟", approvalCount, approvalCount > 0),
          makeTab("festivals", "音乐节模式", festCount, false),
          makeTab("purchased", "已购票/12306", purchasedCount, false),
          makeTab("stubs", "票根纪念墙", stubCount, false),
          makeTab("discovered", "雷达新发现", discoveredCount, discoveredCount > 0),
          makeTab("artists", "关注艺人库", state.artists.length, false)
        ),
        state.activeTab === "artists"
          ? el(
              "button",
              {
                id: "btn-add-artist",
                type: "button",
                className: "btn btn-primary btn-sm",
                onClick: openAddArtistModal,
              },
              "+ 添加关注乐队/歌手"
            )
          : el(
              "div",
              { className: "row-wrap" },
              el(
                "select",
                {
                  id: "concert-sort-select",
                  className: "sort-select",
                  "aria-label": "排序方式",
                  onChange: (ev) => {
                    state.sortMode = ev.target.value;
                    renderMainBodyOnly();
                  },
                },
                el("option", { value: "show_asc", selected: state.sortMode === "show_asc", text: "按开演时间最近" }),
                el("option", { value: "action_asc", selected: state.sortMode === "action_asc", text: "按抢票/回流节点最近" })
              ),
              el("input", {
                id: "concert-search-input",
                type: "search",
                className: "search-input",
                placeholder: "搜索歌手、城市、批文号、备注...",
                value: state.searchQuery,
                onInput: (ev) => {
                  state.searchQuery = ev.target.value;
                  renderMainBodyOnly();
                },
              })
            )
      ),
      showRegionFilters
        ? el(
            "div",
            { className: "filter-row" },
            el("span", { className: "filter-label", text: "区域筛选：" }),
            Object.entries(state.regions).map(([rCode, rLabel]) =>
              el(
                "button",
                {
                  type: "button",
                  className: state.selectedRegion === rCode ? "chip selected" : "chip",
                  onClick: () => {
                    state.selectedRegion = rCode;
                    state.selectedCity = "all";
                    renderWorkspace();
                  },
                },
                rLabel
              )
            )
          )
        : null,
      showRegionFilters && availableCities.length > 1
        ? el(
            "div",
            { className: "filter-row" },
            el("span", { className: "filter-label", text: "城市筛选：" }),
            el(
              "button",
              {
                type: "button",
                className: state.selectedCity === "all" ? "chip selected" : "chip",
                onClick: () => {
                  state.selectedCity = "all";
                  renderWorkspace();
                },
              },
              "全部城市"
            ),
            availableCities.map((city) =>
              el(
                "button",
                {
                  type: "button",
                  className: state.selectedCity === city ? "chip selected" : "chip",
                  onClick: () => {
                    state.selectedCity = city;
                    renderWorkspace();
                  },
                },
                city
              )
            )
          )
        : null
    );

    const nowMsForArchive = Date.now();
    const pastPurchased = state.concerts.filter((c) => {
      if (c.status !== "purchased") return false;
      const sMs = parseShanghaiEpochMs(c.show_time);
      return Boolean(sMs && nowMsForArchive > sMs + 4 * 3600 * 1000);
    });
    const postShowBanner =
      pastPurchased.length > 0 && state.activeTab !== "stubs"
        ? el(
            "section",
            { className: "archive-prompt-banner" },
            el(
              "span",
              {
                text: `演出落幕归档提醒：你有 ${pastPurchased.length} 场已购票演出已结束（如「${pastPurchased[0].artist_name} · ${pastPurchased[0].city}站」），是否盖章存入票根纪念墙？`,
              }
            ),
            el(
              "button",
              {
                type: "button",
                className: "btn btn-sm btn-primary",
                onClick: () => openStubDiaryModal(pastPurchased[0]),
              },
              "去写票根手账"
            )
          )
        : null;

    const mainContainer = el("main", { id: "workspace-main-body" });
    root.replaceChildren(...[masthead, postShowBanner, spotlightSection, controlsBar, mainContainer].filter(Boolean));
    renderMainBodyOnly();
  }

  function renderMainBodyOnly() {
    const container = document.getElementById("workspace-main-body");
    if (!container) return;

    if (state.activeTab === "artists") {
      container.replaceChildren(renderArtistsView());
      return;
    }
    if (state.activeTab === "festivals") {
      container.replaceChildren(renderFestivalsView());
      return;
    }
    if (state.activeTab === "stubs") {
      container.replaceChildren(renderStubWallView());
      return;
    }

    const portalBanner =
      state.activeTab === "approvals"
        ? el(
            "div",
            { className: "drop-spotlight mb-md" },
            el("div", { className: "section-title mb-sm", text: "省/市文旅局营业性演出准予许可官网直达（早于微博官宣 2–8 周）：" }),
            el(
              "div",
              { className: "row-wrap" },
              state.culturePortals.map((pt) =>
                el(
                  "a",
                  {
                    href: pt.url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                    className: "ext-pill",
                  },
                  pt.name
                )
              ),
              el(
                "button",
                {
                  type: "button",
                  className: "btn btn-sm btn-primary",
                  onClick: () => openConcertModal(null, "paste", SAMPLE_APPROVAL_FILING),
                },
                "+ 粘贴过审公示文本"
              )
            )
          )
        : null;

    const filtered = getFilteredConcerts();
    if (filtered.length === 0) {
      container.replaceChildren(
        ...[
          portalBanner,
          el(
            "div",
            { className: "empty-state" },
            el("h3", { text: "当前视图下暂无演出记录" }),
            el("p", { text: "支持粘贴微博/大麦/文旅局审批文本，或直接拖入长图官宣海报自动识别。" }),
            el(
              "div",
              { className: "center-actions" },
              el(
                "button",
                { type: "button", className: "btn btn-primary", onClick: () => openConcertModal(null, "paste") },
                "+ 智能粘贴文案"
              ),
              el(
                "button",
                { type: "button", className: "btn", onClick: () => openConcertModal(null, "poster") },
                "长图海报识图"
              )
            )
          ),
        ].filter(Boolean)
      );
      return;
    }

    container.replaceChildren(
      ...[portalBanner, el("div", { className: "concert-grid" }, filtered.map(renderConcertTicketCard))].filter(Boolean)
    );
  }

  // ---------------- Concert Ticket-Stub Card (with Features #1, #2, #4, #5, #6) ----------------

  function renderConcertTicketCard(c) {
    const nowMs = Date.now();
    const showMs = parseShanghaiEpochMs(c.show_time);
    const regionText = state.regions[c.region] || "";
    const isDiscovered = c.status === "discovered";
    const isApprovedPending = c.status === "approved_pending";

    // Feature #2: Culture Bureau Approval Banner
    const approvalNode =
      c.approval_doc_no || isApprovedPending
        ? el("div", {
            className: "approval-banner",
            text: `文旅过审：${c.approval_doc_no || "已准予许可"}${c.approval_source ? " · " + c.approval_source : ""}（建议提前订免费取消酒店）`,
          })
        : null;

    // Ticket Rounds + Feature #1: Refund Cutoff & Returned-Ticket Snipers
    const scheduleRows = [];
    for (const r of c.ticket_rounds || []) {
      const rMs = parseShanghaiEpochMs(r.sale_time);
      scheduleRows.push(
        el(
          "div",
          { className: "round-row" },
          el("span", null, el("span", { className: "round-badge", text: `[${r.round_label}] ` }), `${r.sale_time} · ${r.platform || c.platform}`),
          rMs
            ? el("span", {
                className: "round-countdown",
                "data-countdown-ms": String(rMs),
                text: formatCountdownText(rMs, nowMs),
              })
            : null
        )
      );
    }

    for (const rf of c.refund_tiers || []) {
      const rfMs = parseShanghaiEpochMs(rf.cutoff_time);
      const isPurchased = c.status === "purchased";
      const badgeLabel = isPurchased
        ? `[退票截止 ${rf.fee_percent}%] `
        : rf.expect_return_drop
          ? "[回流狙击] "
          : "[停止退票] ";
      scheduleRows.push(
        el(
          "div",
          { className: "round-row refund-tier-row" },
          el("span", null, el("span", { className: "sniper-badge", text: badgeLabel }), `${rf.cutoff_time} · ${rf.tier_label}`),
          rfMs
            ? el("span", {
                className: "round-countdown",
                "data-countdown-ms": String(rfMs),
                text: formatCountdownText(rfMs, nowMs),
              })
            : null
        )
      );
    }

    // Feature #5: Cross-City 12306 High-Speed Rail Module
    const rail = c.rail_plan || {};
    const railNode =
      rail.is_cross_city && c.status !== "attended"
        ? el(
            "div",
            { className: "rail-strip" },
            el("strong", { text: `跨城 12306 联动：${rail.corridor}` }),
            el("span", {
              text: `去程 ${rail.outbound_travel_date} 车票开售：${rail.outbound_12306_sale_time} | 返程开售：${rail.return_12306_sale_time.slice(0, 10)}`,
            })
          )
        : null;

    const makePrepCheck = (field, labelText) => {
      const box = el("input", {
        type: "checkbox",
        checked: Boolean(c[field]),
        onChange: async () => {
          try {
            await apiPost("/api/concerts/quick-patch", { id: c.id, [field]: box.checked });
            c[field] = box.checked;
          } catch (err) {
            box.checked = !box.checked;
            showToast(err.message, true);
          }
        },
      });
      return el("label", { className: "prep-check-label" }, box, labelText);
    };

    return el(
      "article",
      { className: "ticket-card" },
      el(
        "div",
        { className: "ticket-main" },
        el(
          "div",
          { className: "ticket-top-row" },
          el("span", {
            className: "city-stamp",
            text: `${c.city}${regionText && c.region !== "other" ? " · " + regionText : ""}${c.event_kind === "festival" ? " · 音乐节" : ""}`,
          }),
          el("span", {
            className: `status-tag status-${c.status}`,
            text: STATUS_LABELS[c.status] || c.status,
          })
        ),
        el("h3", { className: "ticket-artist", text: c.artist_name }),
        el("p", { className: "ticket-title", text: c.title }),
        el(
          "div",
          { className: "ticket-facts" },
          el(
            "div",
            { className: "ticket-fact-row" },
            el("span", { className: "fact-key", text: "开演" }),
            el("span", {
              className: "fact-val",
              text: `${c.show_time}${showMs && showMs > nowMs ? `（距今 ${Math.max(0, Math.ceil((showMs - nowMs) / 86400000))} 天）` : ""}`,
            })
          ),
          c.venue
            ? el(
                "div",
                { className: "ticket-fact-row" },
                el("span", { className: "fact-key", text: "场馆" }),
                el("span", { className: "fact-val", text: c.venue })
              )
            : null,
          el(
            "div",
            { className: "ticket-fact-row" },
            el("span", { className: "fact-key", text: "票务" }),
            el("span", {
              className: "fact-val",
              text: `${c.platform}${c.price_text ? " · " + c.price_text : ""}`,
            })
          ),
          c.seat_note
            ? el(
                "div",
                { className: "ticket-fact-row" },
                el("span", { className: "fact-key", text: "票夹" }),
                el("span", { className: "fact-val", text: c.seat_note })
              )
            : null,
          c.notes
            ? el(
                "div",
                { className: "ticket-fact-row" },
                el("span", { className: "fact-key", text: "备注" }),
                el("span", { className: "fact-val", text: c.notes })
              )
            : null
        ),
        approvalNode,
        scheduleRows.length > 0 ? el("div", { className: "rounds-list" }, scheduleRows) : null,
        railNode
      ),
      el(
        "div",
        { className: "ticket-stub" },
        !isDiscovered
          ? el(
              "div",
              { className: "prep-checks" },
              c.status !== "purchased" ? makePrepCheck("checklist_want", "已预约想看") : null,
              c.status !== "purchased" ? makePrepCheck("checklist_realname", "已预填实名") : null,
              isApprovedPending || rail.is_cross_city ? makePrepCheck("hotel_booked", "可退酒店已锁") : null,
              rail.is_cross_city ? makePrepCheck("rail_booked", "12306高铁已订") : null
            )
          : null,
        el(
          "div",
          { className: "stub-actions" },
          el(
            "div",
            { className: "stub-actions-group" },
            isDiscovered
              ? el(
                  "button",
                  {
                    type: "button",
                    className: "btn btn-primary btn-sm",
                    onClick: async () => {
                      await apiPost("/api/concerts/quick-patch", { id: c.id, status: "upcoming_drop" });
                      showToast("已收入正式排期追踪！");
                      await refreshWorkspace();
                    },
                  },
                  "收入正式追踪"
                )
              : el(
                  "button",
                  {
                    type: "button",
                    className: "btn btn-sm",
                    onClick: async () => {
                      const nextStatus = c.status === "purchased" ? "upcoming_drop" : "purchased";
                      await apiPost("/api/concerts/quick-patch", { id: c.id, status: nextStatus });
                      showToast(nextStatus === "purchased" ? "恭喜出票！已同步跨城与观演提醒" : "已切换回待抢票");
                      await refreshWorkspace();
                    },
                  },
                  c.status === "purchased" ? "改回待抢票" : "标记已抢到票"
                ),
            el(
              "button",
              {
                type: "button",
                className: "btn btn-sm",
                onClick: () => openStubDiaryModal(c),
              },
              "归档票根手账"
            ),
            c.ticket_url
              ? el(
                  "a",
                  {
                    href: c.ticket_url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                    className: "btn btn-sm",
                  },
                  "票务页"
                )
              : null,
            el("a", { href: `/api/calendar/concert.ics?id=${encodeURIComponent(c.id)}`, className: "btn btn-sm" }, ".ics"),
            c.poster_uuid
              ? el("a", { href: `/api/posters/download?uuid=${encodeURIComponent(c.poster_uuid)}`, className: "btn btn-sm" }, "海报")
              : null
          ),
          el(
            "div",
            { className: "stub-actions-group" },
            el("button", { type: "button", className: "btn btn-quiet btn-sm", onClick: () => openConcertModal(c, "manual") }, "编辑"),
            el(
              "button",
              {
                type: "button",
                className: "btn btn-quiet btn-sm",
                onClick: () =>
                  openConfirmDialog("确认移除该场次？", `${c.artist_name} — ${c.city}站`, "确认移除", async () => {
                    await apiPost("/api/concerts/delete", { id: c.id });
                    showToast("已移除场次");
                    await refreshWorkspace();
                  }),
              },
              "删除"
            )
          )
        )
      )
    );
  }

  // ---------------- Feature #3: Music Festival Mode View (音乐节模式) ----------------

  function renderFestivalsView() {
    const headerBar = el(
      "div",
      { className: "drop-spotlight mb-md" },
      el(
        "div",
        { className: "row-between" },
        el(
          "div",
          null,
          el("h2", { className: "section-title", text: "音乐节拼盘决策台（单日票重合度 & 舞台撞场预警）" }),
          el("p", {
            className: "hint-text m-0",
            text: "自动聚合同一音乐节下所有你关注的乐队，计算哪一天单日票最值，并自动标红时间重叠撞场。",
          })
        ),
        el(
          "button",
          {
            type: "button",
            className: "btn btn-primary btn-sm",
            onClick: () => openConcertModal(null, "paste", SAMPLE_FESTIVAL_TIMETABLE),
          },
          "+ 粘贴音乐节时刻表"
        )
      )
    );

    if (!state.festivalGroups.length) {
      return el(
        "div",
        null,
        headerBar,
        el(
          "div",
          { className: "empty-state" },
          el("h3", { text: "暂无音乐节排期" }),
          el("p", { text: "点击上方「+ 粘贴音乐节时刻表」或运行「巡演雷达扫描」即可聚合草莓/迷笛等音乐节阵容。" })
        )
      );
    }

    const cards = state.festivalGroups.map((fg) =>
      el(
        "article",
        { className: "festival-card" },
        el(
          "div",
          { className: "row-between" },
          el(
            "div",
            null,
            el("span", { className: "city-stamp", text: `${fg.city} · 音乐节拼盘` }),
            el("h3", { className: "ticket-artist mt-md", text: fg.festival_name }),
            el("div", { className: "hint-text", text: `${fg.show_time} · ${fg.venue || "场地待定"} · ${fg.price_text || fg.platform}` })
          ),
          fg.ticket_url
            ? el("a", { href: fg.ticket_url, target: "_blank", rel: "noopener noreferrer", className: "btn btn-sm" }, "打开购票页")
            : null
        ),
        el("div", { className: "festival-rec-banner", text: `购票建议：${fg.best_single_day}` }),
        (fg.clashes || []).map((cl) => el("div", { className: "clash-alert", text: `撞场预警：${cl}` })),
        fg.slots && fg.slots.length > 0
          ? el(
              "div",
              { className: "slot-table" },
              fg.slots.map((s) =>
                el(
                  "div",
                  { className: "slot-pill" },
                  el("strong", { text: `${s.artist} ` }),
                  el("div", { className: "hint-text", text: `${s.day_date || ""} · ${s.stage || "舞台"} ${s.set_start || ""}${s.set_end ? "-" + s.set_end : ""}` })
                )
              )
            )
          : el("div", { className: "hint-text", text: `关联乐队：${(fg.matched_artists || []).join(" / ")}（在编辑中补充具体出场时间即可开启撞场检测）` })
      )
    );

    return el("div", null, headerBar, cards);
  }

  // ---------------- Feature #6: Collectible Ticket-Stub Wall (票根纪念墙) ----------------

  function renderStubWallView() {
    const st = state.stubStats || {};
    const attendedList = state.concerts.filter((c) => c.status === "attended");

    const statsRow = el(
      "div",
      { className: "stats-summary-grid" },
      el("div", { className: "stat-tile" }, el("div", { className: "stat-label", text: "累计亲历现场" }), el("div", { className: "stat-value", text: `${st.attended_count || 0} 场` })),
      el(
        "div",
        { className: "stat-tile" },
        el("div", { className: "stat-label", text: "点亮观演城市" }),
        el("div", { className: "stat-value", text: `${st.unlocked_city_count || 0} 城` }),
        st.unlocked_cities && st.unlocked_cities.length
          ? el("div", { className: "hint-text", text: st.unlocked_cities.join(" · ") })
          : null
      ),
      el("div", { className: "stat-tile" }, el("div", { className: "stat-label", text: "累计票面投入" }), el("div", { className: "stat-value", text: `¥${st.total_spent_yuan || 0}` })),
      el("div", { className: "stat-tile" }, el("div", { className: "stat-label", text: "场馆视听均分" }), el("div", { className: "stat-value", text: st.avg_venue_rating ? `${st.avg_venue_rating} ★` : "—" }))
    );

    if (attendedList.length === 0) {
      return el(
        "div",
        null,
        statsRow,
        el(
          "div",
          { className: "empty-state" },
          el("h3", { text: "你的票根纪念墙还空着" }),
          el("p", { text: "在任意演出卡片上点击「归档票根手账」，即可记录实付票价、场馆视线音响评价与安可歌单记忆。" })
        )
      );
    }

    const stubCards = attendedList.map((c) =>
      el(
        "article",
        { className: "collectible-stub" },
        el(
          "div",
          { className: "row-between mb-sm" },
          el("span", { className: "city-stamp", text: `${c.city} · ${c.show_time.slice(0, 10)}` }),
          el("span", { className: "verified-seal", text: "已核验入场 · 纪念票根" })
        ),
        el("h3", { className: "ticket-artist", text: c.artist_name }),
        el("p", { className: "ticket-title", text: `${c.title} @ ${c.venue || c.city}` }),
        el(
          "div",
          { className: "hint-text" },
          `实付票面：¥${c.actual_paid_yuan || "—"} · 座位/区域：${c.seat_note || "现场观演"} · 场馆评分：${c.venue_rating ? "★".repeat(c.venue_rating) : "未评"}`
        ),
        c.seat_view_note
          ? el("div", { className: "diary-box", text: `视线与声场评价：${c.seat_view_note}` })
          : null,
        c.setlist_note
          ? el("div", { className: "diary-box", text: `歌单与现场记忆：${c.setlist_note}` })
          : null,
        el(
          "div",
          { className: "modal-actions" },
          el("button", { type: "button", className: "btn btn-sm", onClick: () => openStubDiaryModal(c) }, "编辑手账记忆")
        )
      )
    );

    return el("div", null, statsRow, el("div", { className: "concert-grid" }, stubCards));
  }

  function openStubDiaryModal(c) {
    const paidIn = el("input", { type: "number", value: String(c.actual_paid_yuan || ""), placeholder: "如：680" });
    const seatIn = el("input", { type: "text", value: c.seat_note || "", placeholder: "如：看台 218区 6排 / 站席前排中轴" });
    const ratingSel = el(
      "select",
      null,
      [5, 4, 3, 2, 1].map((n) =>
        el("option", { value: String(n), selected: (c.venue_rating || 5) === n, text: `${"★".repeat(n)}（${n}分）` })
      )
    );
    const viewArea = el("textarea", {
      value: c.seat_view_note || "",
      placeholder: "记录该场馆区域的视线遮挡情况、音响混响质量、空调与散场地铁攻略（下次抢同场馆可直接参考！）",
    });
    const setlistArea = el("textarea", {
      value: c.setlist_note || "",
      placeholder: "记录最难忘的曲目、安可合唱瞬间或同行伙伴...",
    });
    viewArea.value = c.seat_view_note || "";
    setlistArea.value = c.setlist_note || "";

    const form = el(
      "form",
      {
        onSubmit: async (ev) => {
          ev.preventDefault();
          try {
            await apiPost("/api/concerts/quick-patch", {
              id: c.id,
              status: "attended",
              actual_paid_yuan: Number(paidIn.value || 0),
              seat_note: seatIn.value.trim(),
              venue_rating: Number(ratingSel.value || 5),
              seat_view_note: viewArea.value.trim(),
              setlist_note: setlistArea.value.trim(),
            });
            closeModal();
            state.activeTab = "stubs";
            showToast("已归档至票根纪念墙！");
            await refreshWorkspace();
          } catch (err) {
            showToast(err.message, true);
          }
        },
      },
      el(
        "div",
        { className: "form-grid" },
        el("div", { className: "form-field" }, el("label", { text: "实付票价（元 ¥）" }), paidIn),
        el("div", { className: "form-field" }, el("label", { text: "场馆视听综合评分" }), ratingSel),
        el("div", { className: "form-field full" }, el("label", { text: "座位号 / 观演区域" }), seatIn),
        el("div", { className: "form-field full" }, el("label", { text: "看台视线与音响评价" }), viewArea),
        el("div", { className: "form-field full" }, el("label", { text: "歌单与安可现场手账" }), setlistArea)
      ),
      el(
        "div",
        { className: "modal-actions" },
        el("button", { type: "button", className: "btn", onClick: closeModal }, "取消"),
        el("button", { type: "submit", className: "btn btn-primary" }, "盖章存入票根纪念墙")
      )
    );
    openModal(`归档票根手账 · ${c.artist_name}（${c.city}站）`, form);
  }

  // ---------------- Home City Modal (Feature #5) ----------------

  function openHomeCityModal() {
    const cityIn = el("input", {
      type: "text",
      required: true,
      value: state.user.home_city || "上海",
      placeholder: "如：上海 / 北京 / 广州 / 深圳 / 杭州 / 成都",
    });
    const form = el(
      "form",
      {
        onSubmit: async (ev) => {
          ev.preventDefault();
          try {
            await apiPost("/api/preferences/update", {
              preferred_region: state.user.preferred_region || "all",
              preferred_cities: state.user.preferred_cities || [],
              home_city: cityIn.value.trim(),
            });
            closeModal();
            showToast("常驻出发城市已更新，所有跨城场次的 12306 高铁开售日已重新计算！");
            await refreshWorkspace();
          } catch (err) {
            showToast(err.message, true);
          }
        },
      },
      el(
        "div",
        { className: "form-field" },
        el("label", { text: "常驻出发城市（非本城演出将自动生成提前 15 天 12306 高铁抢票提醒与日历闹钟）" }),
        cityIn
      ),
      el(
        "div",
        { className: "modal-actions" },
        el("button", { type: "button", className: "btn", onClick: closeModal }, "取消"),
        el("button", { type: "submit", className: "btn btn-primary" }, "保存出发城市")
      )
    );
    openModal("设置常驻出发城市 · 12306 高铁联动", form);
  }

  // ---------------- Artists Watchlist View ----------------

  function renderArtistsView() {
    const followedSet = new Set(state.artists.map((a) => a.name));
    const unfollowedPresets = state.presets.filter((p) => !followedSet.has(p.name));

    const liveQueryIn = el("input", {
      id: "inline-artist-search-input",
      type: "text",
      placeholder: "输入任意歌手或乐队名称（如：陈粒 / 毛不易 / 孙燕姿 / 汪苏泷 / 橘子海），回车立即全网检索...",
    });
    const liveResultBox = el("div", { className: "mt-md" });
    const liveSearchBtn = el(
      "button",
      {
        id: "inline-artist-search-btn",
        type: "button",
        className: "btn btn-primary",
        onClick: async () => {
          const q = liveQueryIn.value.trim();
          if (!q) return;
          liveSearchBtn.disabled = true;
          liveResultBox.replaceChildren(el("p", { className: "hint-text", text: `正在联网搜索「${q}」的音乐人档案、中英文别名与近期中国演出...` }));
          try {
            const bundle = await apiGet(`/api/artists/live-search-bundle?q=${encodeURIComponent(q)}`);
            const prof = bundle.primary_profile || { name: q, genre: "", aliases: [] };
            const foundConcerts = bundle.concerts || [];
            const upcomingPresales = bundle.upcoming_presales || [];
            const upcomingCities = bundle.upcoming_cities || [];
            const sLinks = bundle.search_links || {};
            const alreadyFollowed = state.artists.some(
              (a) => a.name.toLowerCase() === String(prof.name || "").toLowerCase()
            );

            liveResultBox.replaceChildren(
              el(
                "div",
                { className: "parsed-stop-box" },
                el(
                  "div",
                  { className: "row-between mb-sm" },
                  el(
                    "div",
                    null,
                    el("strong", { text: `搜索结果：${prof.name}` }),
                    el("div", {
                      className: "hint-text",
                      text: [
                        prof.genre,
                        prof.region_origin,
                        prof.aliases && prof.aliases.length ? `自动识别别名：${prof.aliases.join(" / ")}` : "",
                      ]
                        .filter(Boolean)
                        .join(" · "),
                    })
                  ),
                  el(
                    "button",
                    {
                      type: "button",
                      className: "btn btn-primary btn-sm",
                      onClick: async () => {
                        const res = await apiPost("/api/artists/upsert", {
                          name: prof.name,
                          aliases: prof.aliases || [],
                          genre: prof.genre || "",
                          region_origin: prof.region_origin || "",
                          apple_music_url: prof.apple_music_url || "",
                          auto_discover: true,
                          scan_immediately: true,
                        });
                        let importedCount = res.new_concerts || 0;
                        if (foundConcerts.length > 0) {
                          const batchItems = foundConcerts.map((fc) => ({
                            artist_name: fc.artist_name || prof.name,
                            title: fc.title || `${prof.name} 演唱会`,
                            city: fc.city || "上海",
                            region: fc.region || "other",
                            venue: fc.venue || "",
                            show_time: fc.show_time || "",
                            price_text: fc.price_text || "",
                            platform: fc.platform || "大麦",
                            ticket_url: fc.ticket_url || "",
                            status: fc.status || "upcoming_drop",
                            event_kind: fc.event_kind || "concert",
                            approval_doc_no: fc.approval_doc_no || "",
                            approval_source: fc.approval_source || "",
                            notes: fc.notes || "",
                            ticket_rounds: fc.ticket_rounds || [],
                            refund_tiers: fc.refund_tiers || [],
                          }));
                          const created = await apiPost("/api/concerts/create", { items: batchItems }).catch(() => ({ ids: [] }));
                          importedCount = Math.max(importedCount, (created.ids || []).length);
                        }
                        showToast(
                          upcomingCities.length > 0
                            ? `★ 已收藏「${prof.name}」！即将预售地点：${upcomingCities.join("、")}（共导入 ${importedCount} 场排期并开启提醒）`
                            : `★ 已收藏「${prof.name}」并开启后台巡演与预售雷达！`
                        );
                        await refreshWorkspace();
                      },
                    },
                    alreadyFollowed
                      ? `★ 已收藏「${prof.name}」（同步最新预售场次）`
                      : foundConcerts.length > 0
                        ? `☆ 收藏歌手并开启 ${upcomingCities.join("/")} 预售提醒`
                        : "☆ 收藏歌手并开启自动预售雷达"
                  )
                ),
                upcomingPresales.length > 0
                  ? el(
                      "div",
                      { className: "rounds-list mb-sm" },
                      el("div", {
                        className: "section-title mb-xs",
                        text: `🔔 即将预售门票地点提示（共覆盖 ${upcomingCities.length} 个城市：${upcomingCities.join("、")}）：`,
                      }),
                      upcomingPresales.map((ps) =>
                        el(
                          "div",
                          { className: "round-row" },
                          el(
                            "span",
                            {
                              text: `📍 [${ps.city}站] ${ps.presale_label}：${ps.presale_time ? `${ps.presale_time} 开抢` : `演出日 ${ps.show_time}`} · ${ps.platform} · ${ps.venue || "场馆待公布"}`,
                            }
                          ),
                          el("span", { className: "round-badge", text: ps.price_text || ps.platform })
                        )
                      )
                    )
                  : el("p", {
                      className: "hint-text mb-sm",
                      text: "暂未检出该歌手已定档的近期预售时间；点击右上角「☆ 收藏歌手」后后台每 6 小时自动扫描新排期，也可点下方平台直达核查：",
                    }),
                el(
                  "div",
                  { className: "platform-links" },
                  sLinks.damai ? el("a", { href: sLinks.damai, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "大麦直达搜索") : null,
                  sLinks.maoyan ? el("a", { href: sLinks.maoyan, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "猫眼直达搜索") : null,
                  sLinks.showstart ? el("a", { href: sLinks.showstart, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "秀动直达搜索") : null,
                  sLinks.livenation ? el("a", { href: sLinks.livenation, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "Live Nation中国") : null,
                  sLinks.songkick ? el("a", { href: sLinks.songkick, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "Songkick全球排期") : null,
                  sLinks.moretickets ? el("a", { href: sLinks.moretickets, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "摩天轮搜索") : null,
                  sLinks.weibo ? el("a", { href: sLinks.weibo, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "微博查最新官宣") : null
                )
              )
            );
          } catch (err) {
            liveResultBox.replaceChildren();
            showToast(err.message, true);
          } finally {
            liveSearchBtn.disabled = false;
          }
        },
      },
      "搜索歌手与近期演出"
    );
    liveQueryIn.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        liveSearchBtn.click();
      }
    });

    const liveSearchBanner = el(
      "div",
      { className: "drop-spotlight mb-md" },
      el("div", { className: "section-title mb-sm", text: "自己输入任意歌手 / 乐队名称（系统自动查曲库别名 + 搜近期中国演出）：" }),
      el("div", { className: "row-gap" }, liveQueryIn, liveSearchBtn),
      liveResultBox
    );

    const quickAddBar =
      unfollowedPresets.length > 0
        ? el(
            "div",
            { className: "drop-spotlight mb-md" },
            el("div", { className: "section-title mb-sm", text: "热门巡演乐队与歌手一键关注：" }),
            el(
              "div",
              { className: "preset-picker m-0" },
              unfollowedPresets.map((p) =>
                el(
                  "button",
                  {
                    type: "button",
                    className: "chip",
                    onClick: async () => {
                      const res = await apiPost("/api/artists/upsert", {
                        name: p.name,
                        aliases: p.aliases,
                        genre: p.genre,
                        region_origin: p.region_origin,
                        auto_discover: true,
                        scan_immediately: true,
                      });
                      showToast(
                        res.new_concerts > 0
                          ? `已关注 ${p.name} 并自动发现 ${res.new_concerts} 场演出！`
                          : `已关注 ${p.name}`
                      );
                      await refreshWorkspace();
                    },
                  },
                  `+ ${p.name}`
                )
              )
            )
          )
        : null;

    const cards = state.artists.map((a) => {
      const links = a.search_links || {};
      const artistUpcoming = state.concerts.filter(
        (c) =>
          c.status !== "attended" &&
          (c.artist_id === a.id || String(c.artist_name || "").includes(a.name))
      );
      const presaleLines = [];
      for (const c of artistUpcoming) {
        if (c.ticket_rounds && c.ticket_rounds.length > 0) {
          for (const r of c.ticket_rounds) {
            presaleLines.push(`🔔 ${c.city}站（${r.round_label}）：${r.sale_time} @ ${r.platform || c.platform}`);
          }
        } else if (c.status === "approved_pending") {
          presaleLines.push(`🏛️ ${c.city}站：文旅已过审待定档预售（演出日 ${c.show_time.slice(0, 10)}）`);
        }
      }

      return el(
        "div",
        { className: "artist-card" },
        el(
          "div",
          { className: "artist-header" },
          el(
            "div",
            null,
            el("h3", { className: "artist-name", text: `★ ${a.name}` }),
            el("div", {
              className: "artist-meta",
              text:
                [a.genre, a.region_origin, a.aliases && a.aliases.length ? `别名: ${a.aliases.join("/")}` : ""]
                  .filter(Boolean)
                  .join(" · ") || "已开启巡演追踪",
            })
          ),
          el(
            "button",
            {
              type: "button",
              className: "btn btn-sm",
              onClick: async (ev) => {
                const btn = ev.currentTarget;
                btn.disabled = true;
                try {
                  const res = await apiPost("/api/discover/run", { artist_id: a.id });
                  showToast(
                    res.new_concerts > 0
                      ? `为 ${a.name} 发现 ${res.new_concerts} 场新演出！已放入「雷达新发现」`
                      : `已扫描秀动公开排期，${a.name} 暂无未收录新场次`
                  );
                  await refreshWorkspace();
                } catch (err) {
                  showToast(err.message, true);
                } finally {
                  btn.disabled = false;
                }
              },
            },
            "扫描秀动排期"
          )
        ),
        presaleLines.length > 0
          ? el(
              "div",
              { className: "rounds-list mb-xs" },
              presaleLines.slice(0, 4).map((ln) => el("div", { className: "round-row", text: ln }))
            )
          : el("div", { className: "hint-text mb-xs", text: "暂无已录入的近期预售节点（可在上方重新搜索同步或粘贴新官宣）" }),
        el(
          "div",
          { className: "platform-links" },
          links.damai ? el("a", { href: links.damai, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "搜大麦") : null,
          links.maoyan ? el("a", { href: links.maoyan, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "搜猫眼") : null,
          links.showstart ? el("a", { href: links.showstart, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "搜秀动") : null,
          links.livenation ? el("a", { href: links.livenation, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "Live Nation") : null,
          links.songkick ? el("a", { href: links.songkick, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "Songkick排期") : null,
          links.weibo ? el("a", { href: links.weibo, target: "_blank", rel: "noopener noreferrer", className: "ext-pill" }, "微博查官宣") : null
        ),
        el(
          "div",
          { className: "row-between" },
          el("span", {
            className: "hint-text",
            text: a.last_checked_at
              ? `上次雷达扫描：${new Date(a.last_checked_at * 1000).toLocaleString("zh-CN")}`
              : "尚未执行自动扫描",
          }),
          el(
            "button",
            {
              type: "button",
              className: "btn btn-quiet btn-sm",
              onClick: () =>
                openConfirmDialog("取消关注该音乐人？", `取消关注「${a.name}」`, "确认取消关注", async () => {
                  await apiPost("/api/artists/delete", { id: a.id });
                  await refreshWorkspace();
                }),
            },
            "取消关注"
          )
        )
      );
    });

    return el(
      "div",
      null,
      liveSearchBanner,
      quickAddBar,
      cards.length > 0
        ? el("div", { className: "artist-grid" }, cards)
        : el("div", { className: "empty-state" }, el("h3", { text: "还没有关注任何乐队或歌手" }))
    );
  }

  async function handleRunDiscoveryRadar() {
    const btn = document.getElementById("btn-run-radar");
    if (btn) btn.disabled = true;
    showToast("正在扫描秀动（ShowStart）公开演出与订阅源...");
    try {
      const res = await apiPost("/api/discover/run", {});
      await refreshWorkspace();
      if (res.new_concerts > 0) {
        state.activeTab = "discovered";
        renderWorkspace();
        showToast(`巡演雷达扫描完成：发现 ${res.new_concerts} 场新演出（音乐节已自动同步至音乐节模式）！`);
      } else {
        showToast(`已扫描 ${res.artists_checked} 组关注艺人，暂未发现未收录的新场次`);
      }
    } catch (err) {
      showToast(err.message, true);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function openAddArtistModal() {
    const nameInput = el("input", { id: "artist-name-input", type: "text", placeholder: "输入歌手或乐队名，如：蛙池 / 陈绮贞", required: true });
    const aliasesInput = el("input", { id: "artist-aliases-input", type: "text", placeholder: "选填，逗号分隔，如：万青, OYS" });
    const genreInput = el("input", { id: "artist-genre-input", type: "text", placeholder: "如：独立摇滚 / 华语流行" });
    const rssInput = el("input", { id: "artist-rss-input", type: "url", placeholder: "选填 https://...（支持 RSSHub 微博/文旅局订阅源）" });
    const searchResultsBox = el("div", { className: "preset-picker" });

    const onlineSearchBtn = el(
      "button",
      {
        type: "button",
        className: "btn btn-sm",
        onClick: async () => {
          const q = nameInput.value.trim();
          if (!q) return;
          onlineSearchBtn.disabled = true;
          try {
            const res = await apiGet(`/api/artists/search-online?q=${encodeURIComponent(q)}`);
            searchResultsBox.replaceChildren();
            for (const item of res.results || []) {
              searchResultsBox.appendChild(
                el(
                  "button",
                  {
                    type: "button",
                    className: "chip",
                    onClick: () => {
                      nameInput.value = item.name;
                      genreInput.value = item.genre || "";
                    },
                  },
                  `${item.name}${item.genre ? " · " + item.genre : ""}`
                )
              );
            }
          } catch (err) {
            showToast(err.message, true);
          } finally {
            onlineSearchBtn.disabled = false;
          }
        },
      },
      "在线检索曲库"
    );

    const form = el(
      "form",
      {
        onSubmit: async (ev) => {
          ev.preventDefault();
          try {
            await apiPost("/api/artists/upsert", {
              name: nameInput.value.trim(),
              aliases: aliasesInput.value,
              genre: genreInput.value.trim(),
              custom_rss_url: rssInput.value.trim(),
              auto_discover: true,
            });
            closeModal();
            showToast("已添加到关注艺人库");
            await refreshWorkspace();
          } catch (err) {
            showToast(err.message, true);
          }
        },
      },
      el("div", { className: "form-field" }, el("label", { text: "乐队 / 歌手名称" }), el("div", { className: "row-gap" }, nameInput, onlineSearchBtn), searchResultsBox),
      el("div", { className: "form-field" }, el("label", { text: "常用简称 / 英文名" }), aliasesInput),
      el("div", { className: "form-field" }, el("label", { text: "音乐风格" }), genreInput),
      el("div", { className: "form-field" }, el("label", { text: "自定义 HTTPS RSS 订阅源（可选）" }), rssInput),
      el(
        "div",
        { className: "modal-actions" },
        el("button", { type: "button", className: "btn", onClick: closeModal }, "取消"),
        el("button", { type: "submit", className: "btn btn-primary" }, "保存关注")
      )
    );
    openModal("添加关注的乐队或歌手", form);
  }

  // ---------------- 3-Tab Concert Import / Poster OCR / Manual Editor Modal ----------------

  function openConcertModal(existingConcert, initialMode, prefillText) {
    let mode = existingConcert ? "manual" : initialMode || "paste";
    const wrapper = el("div");

    function renderModalInner() {
      if (state.activePasteHandler) {
        document.removeEventListener("paste", state.activePasteHandler);
        state.activePasteHandler = null;
      }

      const modeSwitch = !existingConcert
        ? el(
            "div",
            { className: "tab-group mb-md" },
            el(
              "button",
              {
                type: "button",
                className: mode === "paste" ? "tab-btn active" : "tab-btn",
                onClick: () => {
                  mode = "paste";
                  renderModalInner();
                },
              },
              "1. 智能粘贴文案"
            ),
            el(
              "button",
              {
                type: "button",
                className: mode === "poster" ? "tab-btn active" : "tab-btn",
                onClick: () => {
                  mode = "poster";
                  renderModalInner();
                },
              },
              "2. 长图官宣海报识图"
            ),
            el(
              "button",
              {
                type: "button",
                className: mode === "manual" ? "tab-btn active" : "tab-btn",
                onClick: () => {
                  mode = "manual";
                  renderModalInner();
                },
              },
              "3. 手动精细录入"
            )
          )
        : null;

      if (mode === "paste") {
        const pasteArea = el("textarea", {
          id: "smart-paste-textarea",
          placeholder: "支持粘贴：①大麦/猫眼/微博官宣（自动提取抢票与阶梯退票回流线） ②省市文旅局过审公示批文 ③草莓/迷笛音乐节分舞台时刻表...",
        });
        if (prefillText) pasteArea.value = prefillText;
        const previewContainer = el("div", { className: "mt-md" });

        const parseBtn = el(
          "button",
          {
            id: "btn-parse-announcement",
            type: "button",
            className: "btn btn-primary",
            onClick: async () => {
              if (!pasteArea.value.trim()) {
                showToast("请先粘贴文本或点击上方任一示例按钮", true);
                return;
              }
              parseBtn.disabled = true;
              try {
                const parsed = await apiPost("/api/concerts/parse", { text: pasteArea.value });
                renderParsedPreview(previewContainer, parsed.items || [], parsed.summary || "");
              } catch (err) {
                showToast(err.message, true);
              } finally {
                parseBtn.disabled = false;
              }
            },
          },
          "智能识别场次、抢票与退票线"
        );

        wrapper.replaceChildren(
          modeSwitch,
          el(
            "div",
            { className: "row-wrap mb-sm" },
            el("button", { type: "button", className: "btn btn-sm", onClick: () => { pasteArea.value = SAMPLE_SINGLE_WITH_REFUND; } }, "示例①：单站抢票+退票回流"),
            el("button", { type: "button", className: "btn btn-sm", onClick: () => { pasteArea.value = SAMPLE_TOUR_MULTI; } }, "示例②：多城巡演"),
            el("button", { type: "button", className: "btn btn-sm", onClick: () => { pasteArea.value = SAMPLE_APPROVAL_FILING; } }, "示例③：省文旅局过审公示"),
            el("button", { type: "button", className: "btn btn-sm", onClick: () => { pasteArea.value = SAMPLE_FESTIVAL_TIMETABLE; } }, "示例④：音乐节撞场时刻表")
          ),
          el("div", { className: "form-field" }, pasteArea),
          el("div", { className: "modal-actions" }, parseBtn),
          previewContainer
        );
      } else if (mode === "poster") {
        wrapper.replaceChildren(modeSwitch, buildPosterImportPanel());
      } else {
        wrapper.replaceChildren(modeSwitch, buildManualConcertForm(existingConcert));
      }
    }

    openModal(existingConcert ? "编辑演出 / 退票回流 / 音乐节阵容" : "新增演唱会 · 音乐节 · 过审早鸟", wrapper);
    renderModalInner();
  }

  // ---------------- Feature #4: Tour Poster Screenshot / OCR Import Panel ----------------

  function buildPosterImportPanel() {
    const previewContainer = el("div", { className: "mt-md" });
    const imgHolder = el("div");
    const statusText = el("p", {
      className: "hint-text",
      text: state.notifSettings && state.notifSettings.vision_api_configured
        ? "已配置 Gemini Vision API Key：上传任意微博长图海报即可自动 OCR 识别全部巡演城市与抢票时间。"
        : "支持上传 PNG/JPG/WEBP（≤5MB，服务端自动剥离 EXIF 隐私元数据）。在「提醒与日历同步」中填入 Gemini API Key 可识别任意海报；也可点击下方按钮一键体验内置长图海报识图流程！",
    });

    async function processPosterPayload(payload) {
      previewContainer.replaceChildren(el("p", { className: "summary-line", text: "正在进行安全像素净化（CDR）与海报文字提取..." }));
      try {
        const res = await apiPost("/api/posters/upload", payload);
        if (res.sample_preview_data_url) {
          imgHolder.replaceChildren(el("img", { className: "poster-preview-img", src: res.sample_preview_data_url, alt: "巡演官宣海报预览" }));
        }
        if (res.warning) {
          showToast(res.warning, true);
        }
        if (res.parsed && res.parsed.items && res.parsed.items.length > 0) {
          renderParsedPreview(previewContainer, res.parsed.items, `海报识图完成：${res.parsed.summary}`);
        } else {
          const manualArea = el("textarea", {
            placeholder: "尚未配置在线 Vision API Key，海报已安全保存（UUID: " + res.poster_uuid.slice(0, 8) + "）。可在此补充海报中的主要文字完成识别：",
          });
          const fallbackBtn = el(
            "button",
            {
              type: "button",
              className: "btn btn-primary btn-sm",
              onClick: async () => {
                const parsed = await apiPost("/api/concerts/parse", { text: manualArea.value });
                for (const it of parsed.items || []) it.poster_uuid = res.poster_uuid;
                renderParsedPreview(previewContainer, parsed.items || [], parsed.summary || "");
              },
            },
            "结合已上传海报解析场次"
          );
          previewContainer.replaceChildren(
            el("p", { className: "hint-text", text: `海报安全校验与净化成功（${res.width}x${res.height} px）。如需全自动识图，可在「提醒与日历同步」中配置 Vision API Key。` }),
            el("div", { className: "form-field" }, manualArea),
            fallbackBtn
          );
        }
      } catch (err) {
        previewContainer.replaceChildren();
        showToast(err.message, true);
      }
    }

    function handleFileObj(file) {
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) {
        showToast("图片超过 5MB 上限，请压缩后再试", true);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        imgHolder.replaceChildren(el("img", { className: "poster-preview-img", src: String(reader.result), alt: "已选海报预览" }));
        processPosterPayload({ filename: file.name || "poster.png", image_base64: String(reader.result) });
      };
      reader.readAsDataURL(file);
    }

    const fileInput = el("input", {
      type: "file",
      accept: "image/png,image/jpeg,image/webp",
      className: "hidden-input",
      onChange: (ev) => {
        if (ev.target.files && ev.target.files[0]) handleFileObj(ev.target.files[0]);
      },
    });

    const dropzone = el(
      "div",
      {
        className: "poster-dropzone",
        onClick: () => fileInput.click(),
        onDragover: (ev) => ev.preventDefault(),
        onDrop: (ev) => {
          ev.preventDefault();
          if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0]) {
            handleFileObj(ev.dataTransfer.files[0]);
          }
        },
      },
      el("strong", { text: "点击选择微博长图官宣海报 / 拖拽图片至此 / 直接按 Ctrl+V 粘贴截图" }),
      el("div", { className: "hint-text mt-md", text: "支持 PNG · JPG · WEBP（最大 5MB · 自动剥离 EXIF 隐私信息）" })
    );

    state.activePasteHandler = (ev) => {
      const items = (ev.clipboardData && ev.clipboardData.items) || [];
      for (const it of items) {
        if (it.type && it.type.startsWith("image/")) {
          ev.preventDefault();
          handleFileObj(it.getAsFile());
          break;
        }
      }
    };
    document.addEventListener("paste", state.activePasteHandler);

    const samplePosterBtn = el(
      "button",
      {
        id: "btn-test-sample-poster",
        type: "button",
        className: "btn btn-sm btn-primary",
        onClick: () => processPosterPayload({ use_sample_poster: true }),
      },
      "一键生成示例巡演长图海报并体验识图导入"
    );

    return el(
      "div",
      null,
      statusText,
      el("div", { className: "mb-sm" }, samplePosterBtn),
      fileInput,
      dropzone,
      imgHolder,
      previewContainer
    );
  }

  function renderParsedPreview(container, items, summary) {
    if (!items.length) {
      container.replaceChildren(el("p", { className: "hint-text", text: "未能识别到有效场次，请切换至手动精细录入。" }));
      return;
    }

    const selectedIndexes = new Set(items.map((_, idx) => idx));
    const stopCards = items.map((item, idx) => {
      const check = el("input", {
        type: "checkbox",
        checked: true,
        onChange: () => {
          if (check.checked) selectedIndexes.add(idx);
          else selectedIndexes.delete(idx);
        },
      });
      const artistIn = el("input", {
        type: "text",
        value: item.artist_name || "",
        onInput: (e) => { item.artist_name = e.target.value; },
      });
      const cityIn = el("input", {
        type: "text",
        value: item.city || "",
        onInput: (e) => { item.city = e.target.value; },
      });
      const showTimeIn = el("input", {
        type: "text",
        value: item.show_time || "",
        onInput: (e) => { item.show_time = e.target.value; },
      });
      const venueIn = el("input", {
        type: "text",
        value: item.venue || "",
        onInput: (e) => { item.venue = e.target.value; },
      });

      const metaParts = [];
      if (item.approval_doc_no) metaParts.push(`批文：${item.approval_doc_no}`);
      if (item.ticket_rounds && item.ticket_rounds.length) {
        metaParts.push(`抢票：${item.ticket_rounds.map((r) => `${r.round_label} ${r.sale_time}`).join(" / ")}`);
      }
      if (item.refund_tiers && item.refund_tiers.length) {
        metaParts.push(`退票回流节点：${item.refund_tiers.length} 个`);
      }
      if (item.lineup && item.lineup.length) {
        metaParts.push(`音乐节舞台时段：${item.lineup.length} 组`);
      }

      return el(
        "div",
        { className: "parsed-stop-box" },
        el("label", { className: "prep-check-label bold-check" }, check, `场次 ${idx + 1}：${item.title}`),
        el(
          "div",
          { className: "form-grid" },
          el("div", { className: "form-field" }, el("label", { text: "艺人 / 阵容" }), artistIn),
          el("div", { className: "form-field" }, el("label", { text: "城市" }), cityIn),
          el("div", { className: "form-field" }, el("label", { text: "演出时间" }), showTimeIn),
          el("div", { className: "form-field" }, el("label", { text: "场馆" }), venueIn)
        ),
        el("div", { className: "hint-text", text: metaParts.join(" · ") || "常规演出场次" })
      );
    });

    const saveBatchBtn = el(
      "button",
      {
        type: "button",
        className: "btn btn-primary",
        onClick: async () => {
          const chosen = items.filter((_, idx) => selectedIndexes.has(idx));
          if (!chosen.length) {
            showToast("请至少勾选一场演出", true);
            return;
          }
          saveBatchBtn.disabled = true;
          try {
            await apiPost("/api/concerts/create", { items: chosen, auto_follow_artist: true });
            closeModal();
            showToast(`成功导入 ${chosen.length} 场排期！`);
            await refreshWorkspace();
          } catch (err) {
            showToast(err.message, true);
          } finally {
            saveBatchBtn.disabled = false;
          }
        },
      },
      `一键导入所选场次（${items.length}）`
    );

    setChildren(
      container,
      el("p", { className: "summary-line", text: summary }),
      stopCards,
      el("div", { className: "modal-actions" }, saveBatchBtn)
    );
  }

  // ---------------- Manual Concert / Refund Tiers / Festival Lineup Form ----------------

  function buildManualConcertForm(c) {
    const artistIn = el("input", { type: "text", required: true, value: c ? c.artist_name : "", placeholder: "如：落日飞车" });
    const kindSel = el(
      "select",
      null,
      el("option", { value: "concert", selected: !c || c.event_kind !== "festival", text: "专场演唱会 / Livehouse" }),
      el("option", { value: "festival", selected: c && c.event_kind === "festival", text: "音乐节拼盘（启用撞场与单日票分析）" })
    );
    const titleIn = el("input", { type: "text", value: c ? c.title : "", placeholder: "如：2026 巡回演唱会（上海站）" });
    const cityIn = el("input", { type: "text", required: true, value: c ? c.city : "上海", placeholder: "如：上海 / 南京 / 深圳" });
    const venueIn = el("input", { type: "text", value: c ? c.venue : "", placeholder: "如：梅赛德斯-奔驰文化中心" });
    const showTimeIn = el("input", { type: "text", required: true, value: c ? c.show_time : "2026-12-20 19:30", placeholder: "YYYY-MM-DD HH:MM" });
    const priceIn = el("input", { type: "text", value: c ? c.price_text : "", placeholder: "如：¥380-1280" });
    const platformSel = el("select", null, PLATFORMS.map((p) => el("option", { value: p, selected: c && c.platform === p, text: p })));
    const statusSel = el(
      "select",
      null,
      Object.entries(STATUS_LABELS)
        .filter(([k]) => k !== "discovered")
        .map(([k, lbl]) => el("option", { value: k, selected: c ? c.status === k : k === "upcoming_drop", text: lbl }))
    );
    const approvalDocIn = el("input", { type: "text", value: c ? c.approval_doc_no || "" : "", placeholder: "选填，如：沪文旅许〔2026〕4812号" });
    const approvalSourceIn = el("input", { type: "text", value: c ? c.approval_source || "" : "", placeholder: "选填，如：上海市文化和旅游局" });
    const seatIn = el("input", { type: "text", value: c ? c.seat_note : "", placeholder: "选填：座位号或票夹备注" });
    const urlIn = el("input", { type: "url", value: c ? c.ticket_url : "", placeholder: "https://..." });
    const notesArea = el("textarea", {
      value: c ? c.notes || "" : "",
      placeholder: "选填：个人蹲票策略、同行好友或行程备忘...",
    });
    notesArea.value = c ? c.notes || "" : "";

    const roundsData =
      c && c.ticket_rounds && c.ticket_rounds.length
        ? c.ticket_rounds.map((r) => ({ ...r }))
        : [{ round_label: "一开", sale_time: "", platform: "大麦", booking_url: "" }];

    const refundsData =
      c && c.refund_tiers && c.refund_tiers.length
        ? c.refund_tiers.map((rf) => ({ ...rf }))
        : [];

    const lineupData =
      c && c.lineup && c.lineup.length
        ? c.lineup.map((sl) => ({ ...sl }))
        : [];

    const roundsContainer = el("div");
    const refundsContainer = el("div");
    const lineupContainer = el("div");

    function renderRoundInputs() {
      setChildren(
        roundsContainer,
        roundsData.map((r, idx) =>
          el(
            "div",
            { className: "round-input-grid" },
            el(
              "select",
              { onChange: (e) => { r.round_label = e.target.value; } },
              ["优先购", "一开", "二开", "回流蹲守"].map((lbl) =>
                el("option", { value: lbl, selected: r.round_label === lbl, text: lbl })
              )
            ),
            el("input", {
              type: "text",
              value: r.sale_time || "",
              placeholder: "YYYY-MM-DD HH:MM（如 2026-11-25 12:18）",
              onInput: (e) => { r.sale_time = e.target.value; },
            }),
            el(
              "select",
              { onChange: (e) => { r.platform = e.target.value; } },
              PLATFORMS.map((p) => el("option", { value: p, selected: (r.platform || "大麦") === p, text: p }))
            ),
            el("button", { type: "button", className: "btn btn-quiet btn-sm", onClick: () => { roundsData.splice(idx, 1); renderRoundInputs(); } }, "移除")
          )
        )
      );
    }

    function renderRefundInputs() {
      setChildren(
        refundsContainer,
        refundsData.map((rf, idx) =>
          el(
            "div",
            { className: "round-input-grid" },
            el("input", {
              type: "text",
              value: rf.tier_label || "无条件退截止",
              onInput: (e) => { rf.tier_label = e.target.value; },
            }),
            el("input", {
              type: "text",
              value: rf.cutoff_time || "",
              placeholder: "截止时间 YYYY-MM-DD HH:MM",
              onInput: (e) => { rf.cutoff_time = e.target.value; },
            }),
            el(
              "select",
              { onChange: (e) => { rf.fee_percent = Number(e.target.value); rf.expect_return_drop = rf.fee_percent < 100; } },
              [0, 10, 20, 30, 50, 100].map((pct) =>
                el("option", { value: String(pct), selected: Number(rf.fee_percent || 0) === pct, text: pct === 100 ? "停止退票" : `手续费 ${pct}%` })
              )
            ),
            el("button", { type: "button", className: "btn btn-quiet btn-sm", onClick: () => { refundsData.splice(idx, 1); renderRefundInputs(); } }, "移除")
          )
        )
      );
    }

    function renderLineupInputs() {
      setChildren(
        lineupContainer,
        lineupData.map((sl, idx) =>
          el(
            "div",
            { className: "slot-input-grid" },
            el("input", { type: "text", value: sl.artist || "", placeholder: "乐队名", onInput: (e) => { sl.artist = e.target.value; } }),
            el("input", { type: "text", value: sl.stage || "主舞台", placeholder: "舞台", onInput: (e) => { sl.stage = e.target.value; } }),
            el("input", { type: "text", value: sl.day_date || showTimeIn.value.slice(0, 10), placeholder: "YYYY-MM-DD", onInput: (e) => { sl.day_date = e.target.value; } }),
            el("input", { type: "text", value: sl.set_start || "", placeholder: "19:30", onInput: (e) => { sl.set_start = e.target.value; } }),
            el("input", { type: "text", value: sl.set_end || "", placeholder: "20:15", onInput: (e) => { sl.set_end = e.target.value; } }),
            el("button", { type: "button", className: "btn btn-quiet btn-sm", onClick: () => { lineupData.splice(idx, 1); renderLineupInputs(); } }, "移除")
          )
        )
      );
    }

    renderRoundInputs();
    renderRefundInputs();
    renderLineupInputs();

    return el(
      "form",
      {
        onSubmit: async (ev) => {
          ev.preventDefault();
          const payload = {
            id: c ? c.id : undefined,
            artist_name: artistIn.value.trim(),
            event_kind: kindSel.value,
            festival_name: kindSel.value === "festival" ? titleIn.value.trim() : "",
            title: titleIn.value.trim(),
            city: cityIn.value.trim(),
            venue: venueIn.value.trim(),
            show_time: showTimeIn.value.trim(),
            price_text: priceIn.value.trim(),
            platform: platformSel.value,
            ticket_url: urlIn.value.trim(),
            status: statusSel.value,
            approval_doc_no: approvalDocIn.value.trim(),
            approval_source: approvalSourceIn.value.trim(),
            poster_uuid: c ? c.poster_uuid : "",
            seat_note: seatIn.value.trim(),
            notes: notesArea.value.trim(),
            source_type: c ? c.source_type || "manual" : "manual",
            checklist_want: c ? c.checklist_want : false,
            checklist_realname: c ? c.checklist_realname : false,
            checklist_alarm: c ? c.checklist_alarm : false,
            hotel_booked: c ? c.hotel_booked : false,
            rail_booked: c ? c.rail_booked : false,
            actual_paid_yuan: c ? c.actual_paid_yuan : 0,
            venue_rating: c ? c.venue_rating : 0,
            seat_view_note: c ? c.seat_view_note : "",
            setlist_note: c ? c.setlist_note : "",
            ticket_rounds: roundsData.filter((r) => r.sale_time && r.sale_time.trim()),
            refund_tiers: refundsData.filter((rf) => rf.cutoff_time && rf.cutoff_time.trim()),
            lineup: lineupData.filter((sl) => sl.artist && sl.artist.trim()),
          };
          try {
            if (c) {
              await apiPost("/api/concerts/update", payload);
              showToast("场次与节点已更新");
            } else {
              await apiPost("/api/concerts/create", payload);
              showToast("新场次已添加");
            }
            closeModal();
            await refreshWorkspace();
          } catch (err) {
            showToast(err.message, true);
          }
        },
      },
      el(
        "div",
        { className: "form-grid" },
        el("div", { className: "form-field" }, el("label", { text: "歌手 / 乐队 *" }), artistIn),
        el("div", { className: "form-field" }, el("label", { text: "演出类型" }), kindSel),
        el("div", { className: "form-field full" }, el("label", { text: "演出 / 音乐节名称" }), titleIn),
        el("div", { className: "form-field" }, el("label", { text: "城市 *" }), cityIn),
        el("div", { className: "form-field" }, el("label", { text: "演出场馆" }), venueIn),
        el("div", { className: "form-field" }, el("label", { text: "演出时间（北京时间）*" }), showTimeIn),
        el("div", { className: "form-field" }, el("label", { text: "票务平台" }), platformSel),
        el("div", { className: "form-field" }, el("label", { text: "票价区间" }), priceIn),
        el("div", { className: "form-field" }, el("label", { text: "追踪状态" }), statusSel),
        el("div", { className: "form-field" }, el("label", { text: "文旅审批文号（可选）" }), approvalDocIn),
        el("div", { className: "form-field" }, el("label", { text: "审批公示部门（可选）" }), approvalSourceIn),
        el("div", { className: "form-field full" }, el("label", { text: "座位 / 票夹备注" }), seatIn),
        el("div", { className: "form-field full" }, el("label", { text: "购票链接（仅支持 https://）" }), urlIn),
        el("div", { className: "form-field full" }, el("label", { text: "个人备注 / 蹲票备忘" }), notesArea)
      ),
      el(
        "div",
        { className: "form-field full" },
        el(
          "div",
          { className: "row-between mb-sm" },
          el("label", { text: "抢票轮次提醒（优先购 / 一开 / 二开）" }),
          el("button", { type: "button", className: "btn btn-sm", onClick: () => { roundsData.push({ round_label: "二开", sale_time: "", platform: platformSel.value, booking_url: "" }); renderRoundInputs(); } }, "+ 增加抢票轮次")
        ),
        roundsContainer
      ),
      el(
        "div",
        { className: "form-field full" },
        el(
          "div",
          { className: "row-between mb-sm" },
          el("label", { text: "阶梯退票截止线 & 回流票狙击窗口" }),
          el(
            "div",
            { className: "row-gap" },
            el(
              "button",
              {
                type: "button",
                className: "btn btn-sm",
                onClick: async () => {
                  const firstSale = roundsData[0] && roundsData[0].sale_time ? roundsData[0].sale_time : "";
                  const res = await apiPost("/api/concerts/generate-refund-tiers", {
                    first_sale_time: firstSale,
                    show_time: showTimeIn.value.trim(),
                  });
                  refundsData.splice(0, refundsData.length, ...(res.refund_tiers || []));
                  renderRefundInputs();
                  showToast("已按大麦强实名标准生成阶梯退票与回流时间线");
                },
              },
              "按大麦标准一键生成退票/回流线"
            ),
            el("button", { type: "button", className: "btn btn-sm", onClick: () => { refundsData.push({ tier_label: "20%手续费截止", cutoff_time: "", fee_percent: 20, expect_return_drop: true }); renderRefundInputs(); } }, "+ 手动添加节点")
          )
        ),
        refundsContainer
      ),
      el(
        "div",
        { className: "form-field full" },
        el(
          "div",
          { className: "row-between mb-sm" },
          el("label", { text: "音乐节分舞台阵容时刻表（用于单日票推荐与撞场冲突检测）" }),
          el("button", { type: "button", className: "btn btn-sm", onClick: () => { kindSel.value = "festival"; lineupData.push({ artist: "", stage: "主舞台", day_date: showTimeIn.value.slice(0, 10), set_start: "20:00", set_end: "20:45" }); renderLineupInputs(); } }, "+ 添加舞台时段")
        ),
        lineupContainer
      ),
      el(
        "div",
        { className: "modal-actions" },
        el("button", { type: "button", className: "btn", onClick: closeModal }, "取消"),
        el("button", { type: "submit", className: "btn btn-primary" }, "保存排期")
      )
    );
  }

  // ---------------- Reminder, Calendar & Vision Key Center Modal ----------------

  function openReminderCenterModal() {
    const ns = state.notifSettings || {};
    const calUrl = `${window.location.origin}${state.user.calendar_feed_path}`;
    const calInput = el("input", { type: "text", readonly: true, value: calUrl });
    const browserPermStatus = "Notification" in window ? Notification.permission : "unsupported";

    const railCheck = el("input", { type: "checkbox", checked: ns.enable_12306_reminders !== false });
    const sniperCheck = el("input", { type: "checkbox", checked: ns.enable_return_sniper !== false });
    const visionIn = el("input", {
      type: "password",
      placeholder: ns.vision_api_configured ? `已加密保存（${ns.vision_api_key_masked}），留空不变` : "AIza...（选填：用于微博官宣长图海报自动 OCR）",
    });

    const barkIn = el("input", {
      type: "url",
      placeholder: ns.bark_configured ? `已加密保存（${ns.bark_url_masked}）` : "https://api.day.app/你的BarkKey",
    });
    const scIn = el("input", {
      type: "password",
      placeholder: ns.serverchan_configured ? `已加密保存（${ns.serverchan_key_masked}）` : "SCT...（Server酱微信推送 SendKey）",
    });
    const tgTokenIn = el("input", {
      type: "password",
      placeholder: ns.telegram_configured ? `已加密保存（${ns.telegram_bot_token_masked}）` : "123456:ABC-DEF...",
    });
    const tgChatIn = el("input", { type: "text", value: ns.telegram_chat_id || "", placeholder: "Telegram Chat ID" });
    const webhookIn = el("input", {
      type: "url",
      placeholder: ns.webhook_configured ? `已加密保存（${ns.webhook_url_masked}）` : "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    });
    const smtpHostIn = el("input", { type: "text", value: ns.smtp_host || "", placeholder: "如 smtp.gmail.com 或 smtp.qq.com" });
    const smtpPortIn = el("input", { type: "number", value: String(ns.smtp_port || 587) });
    const smtpUserIn = el("input", { type: "text", placeholder: ns.smtp_user_masked || "发件邮箱账号" });
    const smtpPassIn = el("input", { type: "password", placeholder: ns.smtp_pass_configured ? "已加密保存，留空不变" : "SMTP 授权码" });
    const notifyEmailIn = el("input", { type: "email", placeholder: ns.notify_email_masked || "接收提醒的邮箱地址" });

    const makeTestBtn = (channelKey, labelText) =>
      el(
        "button",
        {
          type: "button",
          className: "btn btn-sm",
          onClick: async () => {
            try {
              const res = await apiPost("/api/notifications/test", { channel: channelKey });
              const st = (res.outcomes || {})[channelKey] || "sent";
              showToast(`${labelText}测试结果：${st}`);
            } catch (err) {
              showToast(err.message, true);
            }
          },
        },
        `测试${labelText}`
      );

    const content = el(
      "div",
      null,
      el(
        "section",
        { className: "parsed-stop-box" },
        el("h3", { className: "subhead-title", text: "1. 日历自动同步（含抢票 · 退票回流 · 跨城12306高铁 · 开演四重提醒）" }),
        el("div", { className: "row-gap mb-sm" }, calInput),
        el(
          "div",
          { className: "row-wrap" },
          el(
            "button",
            {
              type: "button",
              className: "btn btn-sm btn-primary",
              onClick: async () => {
                try {
                  if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(calInput.value);
                  } else {
                    calInput.select();
                    document.execCommand("copy");
                  }
                  showToast("日历订阅链接已复制！");
                } catch (_clipErr) {
                  calInput.select();
                  showToast("已选中链接，请按 Ctrl+C / Cmd+C 复制");
                }
              },
            },
            "复制日历订阅链接"
          ),
          el("a", { href: state.user.calendar_feed_path, className: "btn btn-sm" }, "下载全部排期 .ics"),
          el(
            "button",
            {
              type: "button",
              className: "btn btn-quiet btn-sm",
              onClick: async () => {
                const res = await apiPost("/api/calendar/rotate-token", {});
                state.user.calendar_feed_path = res.calendar_feed_path;
                calInput.value = `${window.location.origin}${res.calendar_feed_path}`;
                showToast("已重置订阅令牌");
              },
            },
            "重置订阅链接令牌"
          )
        ),
        window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"
          ? el("p", {
              className: "hint-text mt-md m-0",
              text: "提示：本机 localhost 运行时，推荐直接点击「下载全部排期 .ics」一键导入系统日历；部署至公网 HTTPS（如 Render / Railway）后即可直接在手机日历中添加订阅链接自动同步。",
            })
          : null
      ),
      el(
        "section",
        { className: "parsed-stop-box" },
        el("h3", { className: "subhead-title", text: "2. 浏览器桌面强提醒" }),
        el(
          "div",
          { className: "row-wrap" },
          el("span", { className: "hint-text", text: `当前浏览器通知权限：${browserPermStatus}` }),
          "Notification" in window && Notification.permission !== "granted"
            ? el(
                "button",
                {
                  type: "button",
                  className: "btn btn-sm btn-primary",
                  onClick: async () => {
                    const p = await Notification.requestPermission();
                    showToast(p === "granted" ? "浏览器通知权限已开启！" : "请在浏览器地址栏允许通知", p !== "granted");
                    openReminderCenterModal();
                  },
                },
                "开启浏览器通知权限"
              )
            : null,
          el(
            "button",
            {
              type: "button",
              className: "btn btn-sm",
              onClick: () => {
                if ("Notification" in window && Notification.permission === "granted") {
                  new Notification("现场回响 · 抢票与回流提醒测试", {
                    body: "万能青年旅店（上海站）将在 5 分钟后开启抢票！请确认实名观演人。",
                  });
                } else {
                  showToast("请先点击开启浏览器通知权限");
                }
              },
            },
            "发送浏览器测试弹窗"
          )
        )
      ),
      el(
        "form",
        {
          onSubmit: async (ev) => {
            ev.preventDefault();
            try {
              const res = await apiPost("/api/settings/notifications", {
                browser_enabled: true,
                enable_12306_reminders: railCheck.checked,
                enable_return_sniper: sniperCheck.checked,
                vision_api_key: visionIn.value.trim(),
                bark_url: barkIn.value.trim(),
                serverchan_key: scIn.value.trim(),
                telegram_bot_token: tgTokenIn.value.trim(),
                telegram_chat_id: tgChatIn.value.trim(),
                webhook_url: webhookIn.value.trim(),
                smtp_host: smtpHostIn.value.trim(),
                smtp_port: Number(smtpPortIn.value || 587),
                smtp_user: smtpUserIn.value.trim(),
                smtp_pass: smtpPassIn.value,
                notify_email: notifyEmailIn.value.trim(),
              });
              state.notifSettings = res.notification_settings;
              showToast("加密配置已保存！");
              openReminderCenterModal();
            } catch (err) {
              showToast(err.message, true);
            }
          },
        },
        el("h3", { className: "subhead-title mt-md", text: "3. 智能场景提醒开关 & 海报 OCR 密钥 & 手机推送" }),
        el(
          "div",
          { className: "row-wrap mb-sm" },
          el("label", { className: "prep-check-label" }, sniperCheck, "启用阶梯退票截止与回流票狙击提醒"),
          el("label", { className: "prep-check-label" }, railCheck, "启用跨城观演 12306 高铁开售提醒")
        ),
        el(
          "div",
          { className: "form-grid" },
          el("div", { className: "form-field full" }, el("label", { text: "Gemini Vision API Key（用于长图官宣海报 OCR 自动识图，Fernet 加密存储）" }), visionIn),
          el("div", { className: "form-field full" }, el("div", { className: "row-between" }, el("label", { text: "Bark iOS 强提醒地址" }), makeTestBtn("bark", "Bark")), barkIn),
          el("div", { className: "form-field full" }, el("div", { className: "row-between" }, el("label", { text: "Server酱 SendKey（微信直推）" }), makeTestBtn("serverchan", "微信推送")), scIn),
          el("div", { className: "form-field" }, el("label", { text: "Telegram Bot Token" }), tgTokenIn),
          el("div", { className: "form-field" }, el("div", { className: "row-between" }, el("label", { text: "Telegram Chat ID" }), makeTestBtn("telegram", "TG")), tgChatIn),
          el("div", { className: "form-field full" }, el("div", { className: "row-between" }, el("label", { text: "飞书 / 企业微信 / 钉钉 / HTTPS Webhook" }), makeTestBtn("webhook", "Webhook")), webhookIn),
          el("div", { className: "form-field" }, el("label", { text: "SMTP 邮件服务器" }), smtpHostIn),
          el("div", { className: "form-field" }, el("label", { text: "SMTP 端口" }), smtpPortIn),
          el("div", { className: "form-field" }, el("label", { text: "SMTP 发件账号" }), smtpUserIn),
          el("div", { className: "form-field" }, el("label", { text: "SMTP 密码/授权码" }), smtpPassIn),
          el("div", { className: "form-field full" }, el("div", { className: "row-between" }, el("label", { text: "接收提醒的邮箱地址" }), makeTestBtn("email", "邮件")), notifyEmailIn)
        ),
        el(
          "div",
          { className: "modal-actions" },
          el("button", { type: "button", className: "btn", onClick: closeModal }, "关闭"),
          el("button", { type: "submit", className: "btn btn-primary" }, "加密保存全部设置")
        )
      ),
      buildBackupSection()
    );

    openModal("提醒、日历同步与海报 OCR 配置中心", content);
  }

  function buildBackupSection() {
    const restoreInput = el("input", {
      type: "file",
      accept: "application/json,.json",
      className: "hidden-input",
      onChange: (ev) => {
        const file = ev.target.files && ev.target.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) {
          showToast("备份文件超过 2MB 上限", true);
          return;
        }
        const reader = new FileReader();
        reader.onload = async () => {
          try {
            const parsed = JSON.parse(String(reader.result || "{}"));
            const res = await apiPost("/api/backup/import", parsed);
            showToast(`恢复完成：导入 ${res.artists_imported} 组艺人、${res.concerts_imported} 场演出`);
            closeModal();
            await refreshWorkspace();
          } catch (err) {
            showToast(`备份导入失败：${err.message}`, true);
          }
        };
        reader.readAsText(file, "utf-8");
      },
    });

    return el(
      "section",
      { className: "parsed-stop-box mt-md" },
      el("h3", { className: "subhead-title", text: "4. 演出库便携数据备份与恢复（不含密码与加密推送密钥）" }),
      el(
        "div",
        { className: "row-wrap" },
        el("a", { href: "/api/backup/export", className: "btn btn-sm" }, "导出 JSON 备份文件"),
        restoreInput,
        el(
          "button",
          {
            type: "button",
            className: "btn btn-sm",
            onClick: () => restoreInput.click(),
          },
          "从备份文件恢复"
        )
      )
    );
  }

  // ---------------- Live 1-Second Countdown & Browser Notification Ticker ----------------

  function startLiveTicker() {
    if (state.clockTimerId) window.clearInterval(state.clockTimerId);
    state.clockTimerId = window.setInterval(() => {
      const clockNode = document.getElementById("beijing-clock");
      if (clockNode) clockNode.textContent = formatShanghaiNow();

      const nowMs = Date.now();
      const countdownNodes = document.querySelectorAll("[data-countdown-ms]");
      countdownNodes.forEach((node) => {
        const targetMs = Number(node.getAttribute("data-countdown-ms"));
        if (targetMs) node.textContent = formatCountdownText(targetMs, nowMs);
      });

      if (state.authenticated && "Notification" in window && Notification.permission === "granted") {
        for (const c of state.concerts) {
          if (c.status === "purchased" || c.status === "attended" || c.status === "discovered") continue;
          for (const r of c.ticket_rounds || []) {
            const ms = parseShanghaiEpochMs(r.sale_time);
            if (!ms) continue;
            const diffMin = (ms - nowMs) / 60000;
            for (const mark of [60, 15, 5, 1]) {
              if (diffMin <= mark && diffMin > mark - 0.4) {
                const key = `drop:${c.id}:${r.id}:${mark}`;
                if (!state.firedBrowserAlerts.has(key)) {
                  state.firedBrowserAlerts.add(key);
                  new Notification(`抢票倒计时 ${mark} 分钟：${c.artist_name}（${c.city}站）`, {
                    body: `${r.round_label} 将于 ${r.sale_time} 在 ${r.platform || c.platform} 开启！`,
                  });
                }
              }
            }
          }
          for (const rf of c.refund_tiers || []) {
            if (!rf.expect_return_drop) continue;
            const ms = parseShanghaiEpochMs(rf.cutoff_time);
            if (!ms) continue;
            const diffMin = (ms - nowMs) / 60000;
            if (diffMin <= 10 && diffMin > 9.5) {
              const key = `sniper:${c.id}:${rf.id}:10`;
              if (!state.firedBrowserAlerts.has(key)) {
                state.firedBrowserAlerts.add(key);
                new Notification(`回流票狙击预警：${c.artist_name}（${c.city}站）`, {
                  body: `10分钟后跨过「${rf.tier_label}」，请准备刷新票务页面蹲守退票回流！`,
                });
              }
            }
          }
        }
      }
    }, 1000);
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeModal();
  });

  document.addEventListener("DOMContentLoaded", initApp);
})();
