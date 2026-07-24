(() => {
  "use strict";

  const state = {
    games: [],
    gameCode: "HK_MARKSIX",
    dashboard: null,
    run: null,
    mode: "single",
    ticketPage: 0,
    periodPage: 0,
    combinationsOpen: false,
    busy: false,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || "系統暫時無法完成操作");
    return payload;
  }

  function notice(message, error = false) {
    const box = $("#notice");
    box.textContent = message;
    box.classList.toggle("error", error);
    box.classList.remove("hidden");
    clearTimeout(notice.timer);
    notice.timer = setTimeout(() => box.classList.add("hidden"), 5000);
  }

  function combinationCount(n, r) {
    if (r > n) return 0;
    let value = 1;
    for (let i = 1; i <= r; i += 1) value = value * (n - r + i) / i;
    return Math.round(value);
  }

  function currentGame() {
    return state.games.find((game) => game.game_code === state.gameCode);
  }

  function modeLabel(mode) {
    if (mode === "single") return "精選10組";
    return `${mode.replace("wheel", "")}碼包牌`;
  }

  function ball(value, className = "") {
    return `<span class="number-ball ${className}">${String(value).padStart(2, "0")}</span>`;
  }

  function allPoolNumbers(ticket) {
    const groups = Object.entries(ticket?.pools || {});
    return groups.map(([pool, numbers], groupIndex) => ({
      pool,
      numbers,
      groupIndex,
    }));
  }

  function rateText(value) {
    return value === null || value === undefined ? "—" : `${value}%`;
  }

  function comparisonBalls(row, numbers, { special = false } = {}) {
    const hitNumbers = new Set((row.comparison_hit_numbers || []).map(Number));
    const hitPositions = new Set((row.comparison_hit_positions || []).map(Number));
    const ordered = state.dashboard?.game?.game_type === "ordered_digits";
    return (numbers || []).map((number, index) => {
      const hit = !special && (
        ordered ? hitPositions.has(index) : hitNumbers.has(Number(number))
      );
      return `<span class="compare-ball ${hit ? "hit" : ""} ${special ? "special" : ""}">`
        + `${String(number).padStart(2, "0")}</span>`;
    }).join("");
  }

  function setCombinationsOpen(open) {
    state.combinationsOpen = Boolean(open && state.run?.tickets?.length);
    $("#result-section").classList.toggle("hidden", !state.combinationsOpen);
  }

  function renderQuickGames() {
    const preferred = [
      "HK_MARKSIX", "TW_LOTTO649", "TW_SUPER_LOTTO638",
      "TW_DAILY539", "TW_BINGO",
    ];
    $("#quick-games").innerHTML = preferred
      .map((code) => state.games.find((game) => game.game_code === code))
      .filter(Boolean)
      .map((game) => (
        `<button data-game="${esc(game.game_code)}" class="${game.game_code === state.gameCode ? "active" : ""}">`
        + `${esc(game.display_name)}</button>`
      )).join("");
    $("#quick-games").querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        $("#game-select").value = button.dataset.game;
        changeGame(button.dataset.game);
      });
    });
  }

  function renderModes() {
    const game = state.dashboard.game;
    const modes = [{
      code: "single",
      title: "精選10組",
      detail: game.game_type === "high_frequency" ? "依所選星數" : "差異化單式",
    }];
    for (const size of game.wheel_modes) {
      modes.push({
        code: `wheel${size}`,
        title: `${size}碼包牌`,
        detail: `完整 ${combinationCount(size, game.primary_pick_count)} 組`,
      });
    }
    if (!modes.some((item) => item.code === state.mode)) state.mode = "single";
    $("#mode-picker").innerHTML = modes.map((mode) => `
      <button class="mode ${mode.code === state.mode ? "active" : ""}"
              data-mode="${mode.code}" role="radio"
              aria-checked="${mode.code === state.mode}">
        <strong>${esc(mode.title)}</strong><span>${esc(mode.detail)}</span>
      </button>`).join("");
    $("#mode-picker").querySelectorAll(".mode").forEach((button) => {
      button.addEventListener("click", () => {
        state.mode = button.dataset.mode;
        renderModes();
      });
    });
    $("#star-control").classList.toggle("hidden", game.game_type !== "high_frequency");
  }

  function renderDataStatus() {
    const data = state.dashboard.data;
    const badge = $("#data-badge");
    if (data.official_count > 0) {
      badge.textContent = `官方 ${data.official_count.toLocaleString("zh-TW")} 期 · 截至 ${data.latest_draw_date}`;
      badge.classList.remove("fixture");
    } else {
      badge.textContent = `目前使用測試資料 ${data.fixture_count} 期`;
      badge.classList.add("fixture");
    }
    $("#choice-title").textContent = state.dashboard.game.display_name;
  }

  function renderSummary(run) {
    const summary = $("#run-summary");
    if (!run?.tickets?.length) {
      summary.innerHTML = `
        <div class="empty-state"><span class="empty-ball">?</span>
        <h2>尚無本期組合</h2><p>按左側按鈕即可產生並保存。</p></div>`;
      return;
    }
    const first = run.tickets[0];
    const groups = allPoolNumbers(first);
    const balls = groups.map((group) => (
      group.numbers.map((number) => (
        `<span class="summary-ball ${group.groupIndex ? "secondary" : ""}">${String(number).padStart(2, "0")}</span>`
      )).join("")
    )).join('<span class="pool-separator">＋</span>');
    const mode = run.config?.simple_mode || "single";
    summary.innerHTML = `
      <div class="summary-top">
        <div><span>目標期別</span><strong>${esc(run.target_draw_no)}</strong></div>
        <span class="summary-status">${run.locked ? "已保存鎖定" : "已保存"}</span>
      </div>
      <p class="summary-label">${esc(modeLabel(mode))} · 第1組預覽</p>
      <div class="summary-balls">${balls}</div>
      <div class="summary-foot">
        <span>資料截至 ${esc(run.cutoff_draw_no)}</span>
        <span>共 ${run.generated_ticket_count} 組</span>
      </div>
      <button id="open-combinations" class="summary-open">
        查看完整 ${run.generated_ticket_count} 組 <b>→</b>
      </button>`;
    $("#open-combinations").addEventListener("click", () => setCombinationsOpen(true));
  }

  function renderRun(run) {
    state.run = run;
    state.ticketPage = 0;
    renderSummary(run);
    if (!run?.tickets?.length) {
      setCombinationsOpen(false);
      return;
    }
    const mode = run.config?.simple_mode || "single";
    state.mode = mode;
    if (state.dashboard) renderModes();
    $("#result-section").classList.toggle("hidden", !state.combinationsOpen);
    $("#result-title").textContent = `${state.dashboard.game.display_name} · ${modeLabel(mode)}`;
    $("#result-meta").textContent = (
      `目標 ${run.target_draw_no}｜資料截至 ${run.cutoff_draw_no}｜`
      + `${run.generated_ticket_count} 組｜seed ${run.random_seed}`
    );
    $("#export-csv").href = `/api/exports/generation/${run.run_uuid}.csv`;
    const wheelNumbers = run.config?.wheel_numbers || run.wheel_numbers;
    const wheel = $("#wheel-core");
    if (wheelNumbers?.length) {
      wheel.innerHTML = `<strong>核心 ${wheelNumbers.length} 碼</strong>`
        + `<div class="ball-row">${wheelNumbers.map((number) => ball(number)).join("")}</div>`;
      wheel.classList.remove("hidden");
    } else {
      wheel.classList.add("hidden");
    }
    renderTickets();
  }

  function renderTickets() {
    if (!state.run) return;
    const pageSize = window.innerHeight <= 800 ? 6 : 10;
    const pageCount = Math.max(1, Math.ceil(state.run.tickets.length / pageSize));
    state.ticketPage = Math.min(state.ticketPage, pageCount - 1);
    const start = state.ticketPage * pageSize;
    const visibleTickets = state.run.tickets.slice(start, start + pageSize);
    $("#tickets").innerHTML = visibleTickets.map((ticket) => {
      const groups = allPoolNumbers(ticket);
      const pools = groups.map((group) => (
        group.numbers.map((number) => ball(number, group.groupIndex ? "pool-two" : "")).join("")
      )).join('<span class="pool-separator">＋</span>');
      return `<article class="ticket">
        <span class="ticket-index">${String(ticket.ticket_index).padStart(2, "0")}</span>
        <div class="ball-row">${pools}</div>
      </article>`;
    }).join("");
    const pager = $("#ticket-pager");
    pager.classList.toggle("hidden", pageCount <= 1);
    $("#ticket-page").textContent = `第 ${state.ticketPage + 1}／${pageCount} 頁`;
    $("#ticket-prev").disabled = state.ticketPage === 0;
    $("#ticket-next").disabled = state.ticketPage >= pageCount - 1;
  }

  function renderWeekly() {
    const summary = state.dashboard.performance_summary || {};
    const recent = summary.recent_10 || {};
    const latestWeek = summary.latest_week || {};
    const overall = summary.overall || {};
    const periods = state.dashboard.recent_periods || [];
    const periodPageCount = Math.max(1, Math.ceil(periods.length / 5));
    state.periodPage = Math.min(state.periodPage, periodPageCount - 1);
    const visiblePeriods = periods.slice(
      state.periodPage * 5,
      state.periodPage * 5 + 5,
    );
    $("#recent-hit-rate").textContent = rateText(recent.ticket_hit_rate);
    $("#recent-number-accuracy").textContent = rateText(recent.number_accuracy);
    $("#weekly-hit-rate").textContent = rateText(latestWeek.ticket_hit_rate);
    $("#weekly-number-accuracy").textContent = rateText(latestWeek.number_accuracy);
    $("#latest-week-label").textContent = latestWeek.week || "尚無週資料";
    $("#overall-hit-rate").textContent = rateText(overall.ticket_hit_rate);
    $("#overall-number-accuracy").textContent = rateText(overall.number_accuracy);
    $("#weekly-table").innerHTML = visiblePeriods.map((row) => {
      const predicted = comparisonBalls(row, row.predicted_numbers);
      const actual = comparisonBalls(row, row.actual_numbers);
      const special = comparisonBalls(
        row,
        row.actual_special_numbers,
        { special: true },
      );
      return `<article class="period-card">
        <div class="period-id">
          <span>${esc(row.draw_date)}</span>
          <strong>${esc(row.draw_no)}</strong>
        </div>
        <div class="compare-group">
          <span>預測</span><div>${predicted}</div>
        </div>
        <div class="compare-group actual">
          <span>開獎</span><div>${actual}${special ? `<i>＋</i>${special}` : ""}</div>
        </div>
        <div class="period-rate">
          <strong>${rateText(row.comparison_hit_rate)}</strong>
          <small>命中 ${row.comparison_hit_count}/${row.comparison_number_count}</small>
        </div>
      </article>`;
    }).join("");
    $("#weekly-empty").classList.toggle("hidden", periods.length > 0);
    $("#period-pager").classList.toggle("hidden", periodPageCount <= 1);
    $("#period-page").textContent = `第 ${state.periodPage + 1}／${periodPageCount} 頁`;
    $("#period-prev").disabled = state.periodPage === 0;
    $("#period-next").disabled = state.periodPage >= periodPageCount - 1;
    $("#metric-note").textContent = state.dashboard.metric_note;
  }

  function historyPreview(record) {
    const ticket = record.tickets?.[0];
    if (!ticket) return "";
    return allPoolNumbers(ticket).map((group) => (
      group.numbers.map((number) => ball(number)).join("")
    )).join('<span class="pool-separator">＋</span>');
  }

  function renderHistory() {
    const records = state.dashboard.records || [];
    if (!records.length) {
      $("#history-list").innerHTML = '<div class="history-empty">尚無推薦紀錄。產生下期組合後會自動出現在這裡。</div>';
      return;
    }
    $("#history-list").innerHTML = records.slice(0, 3).map((record) => {
      const evaluation = record.evaluation || {};
      const checked = evaluation.status === "completed";
      const best = checked
        ? Math.max(0, ...(evaluation.results || []).map((item) => item.main_hit_count || 0))
        : null;
      const special = checked && (evaluation.results || []).some((item) => item.special_hit);
      const resultText = checked
        ? `最高命中 ${best} 碼${special ? "＋特別號" : ""}`
        : "等待開獎";
      const detail = checked
        ? `已核對 ${evaluation.actual_draw_no || record.target_draw_no}`
        : `目標 ${record.target_draw_no}`;
      return `<article class="history-card">
        <div class="history-period">
          <span>${esc(record.game_name)}</span>
          <strong>${esc(modeLabel(record.config?.simple_mode || "single"))}</strong>
        </div>
        <div class="history-balls">${historyPreview(record)}</div>
        <div class="history-result">
          <strong class="${checked ? "checked" : "waiting"}">${esc(resultText)}</strong>
          <small>${esc(detail)} · ${record.generated_ticket_count}組</small>
        </div>
      </article>`;
    }).join("");
  }

  async function loadDashboard({ autoGenerate = true } = {}) {
    state.dashboard = await api(`/api/simple/dashboard/${encodeURIComponent(state.gameCode)}`);
    renderDataStatus();
    renderModes();
    renderWeekly();
    renderHistory();
    const latest = state.dashboard.latest_recommendation;
    if (latest) {
      renderRun(latest);
    } else if (autoGenerate) {
      await generate(false);
    } else {
      state.run = null;
      renderSummary(null);
      $("#result-section").classList.add("hidden");
    }
  }

  async function changeGame(gameCode) {
    if (!gameCode) return;
    while (state.busy) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      if ($("#game-select").value !== gameCode) return;
    }
    state.gameCode = gameCode;
    state.mode = "single";
    state.run = null;
    state.periodPage = 0;
    setCombinationsOpen(false);
    renderQuickGames();
    $("#run-summary").innerHTML = `
      <div class="empty-state"><span class="empty-ball">…</span>
      <h2>正在準備本期組合</h2><p>讀取最近開獎資料中。</p></div>`;
    try {
      await loadDashboard();
    } catch (error) {
      notice(error.message, true);
      renderSummary(null);
    }
  }

  async function generate(refresh) {
    if (state.busy) return;
    state.busy = true;
    const button = $("#generate");
    button.disabled = true;
    button.querySelector("span").textContent = "正在建立組合…";
    try {
      const run = await api("/api/simple/generate", {
        method: "POST",
        body: JSON.stringify({
          game_code: state.gameCode,
          mode: state.mode,
          ticket_count: 10,
          star_count: Number($("#star-count").value),
          refresh,
        }),
      });
      renderRun(run);
      state.dashboard = await api(`/api/simple/dashboard/${encodeURIComponent(state.gameCode)}`);
      renderDataStatus();
      renderWeekly();
      renderHistory();
      notice(refresh ? "已換一組並保存新紀錄" : "下期組合已保存");
    } catch (error) {
      notice(error.message, true);
    } finally {
      state.busy = false;
      button.disabled = false;
      button.querySelector("span").textContent = "產生／查看下期組合";
    }
  }

  async function init() {
    try {
      const [health, games] = await Promise.all([
        api("/api/health"),
        api("/api/games?include_stats=false"),
      ]);
      $("#health").innerHTML = `<i></i>${esc(health.status === "ok" ? "系統正常" : "需要檢查")}`;
      state.games = games.filter((game) => game.active);
      const preferred = state.games.find((game) => game.game_code === "HK_MARKSIX");
      state.gameCode = preferred?.game_code || state.games[0]?.game_code;
      $("#game-select").innerHTML = state.games.map((game) => (
        `<option value="${esc(game.game_code)}">${esc(game.display_name)}</option>`
      )).join("");
      $("#game-select").value = state.gameCode;
      renderQuickGames();
      await loadDashboard();
    } catch (error) {
      $("#health").textContent = "連線失敗";
      notice(error.message, true);
    }
  }

  $("#game-select").addEventListener("change", (event) => changeGame(event.target.value));
  $("#generate").addEventListener("click", () => generate(false));
  $("#refresh-run").addEventListener("click", () => generate(true));
  $("#close-combinations").addEventListener("click", () => setCombinationsOpen(false));
  $("#period-prev").addEventListener("click", () => {
    state.periodPage = Math.max(0, state.periodPage - 1);
    renderWeekly();
  });
  $("#period-next").addEventListener("click", () => {
    state.periodPage += 1;
    renderWeekly();
  });
  $("#ticket-prev").addEventListener("click", () => {
    state.ticketPage = Math.max(0, state.ticketPage - 1);
    renderTickets();
  });
  $("#ticket-next").addEventListener("click", () => {
    state.ticketPage += 1;
    renderTickets();
  });
  window.addEventListener("resize", () => {
    if (state.run) renderTickets();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.combinationsOpen) setCombinationsOpen(false);
  });
  $("#reload-dashboard").addEventListener("click", async () => {
    try {
      await loadDashboard({ autoGenerate: false });
      notice("推薦與週報已重新整理");
    } catch (error) {
      notice(error.message, true);
    }
  });
  $("#update-data").addEventListener("click", async () => {
    try {
      const job = await api("/api/data/update?scope=all", { method: "POST" });
      notice(`官方資料更新已開始；工作編號 ${job.job_uuid.slice(0, 8)}`);
    } catch (error) {
      notice(error.message, true);
    }
  });
  $("#fullscreen-toggle").addEventListener("click", async () => {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch {
      notice("瀏覽器未允許網頁切換全螢幕，請直接按 F11");
    }
  });
  document.addEventListener("fullscreenchange", () => {
    const button = $("#fullscreen-toggle");
    button.lastChild.textContent = document.fullscreenElement ? " 離開全螢幕" : " 全螢幕";
  });

  init();
})();
