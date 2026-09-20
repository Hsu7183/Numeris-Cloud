(() => {
  "use strict";

  const state = {
    games: [],
    gameCode: "HK_MARKSIX",
    dashboard: null,
    run: null,
    mode: "weekly",
    ticketPage: 0,
    periodPage: 0,
    performanceView: "history",
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
    if (mode === "weekly") return "每週唯一1組";
    if (mode === "coverage") return "覆蓋率優先10組";
    if (mode === "single") return "影片法10組";
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

  function verifiedRate(bucket) {
    return Number(bucket?.evaluated_runs || 0) > 0
      ? rateText(bucket.target_hit_rate)
      : "等待驗證";
  }

  function verifiedAccuracy(bucket) {
    return Number(bucket?.evaluated_runs || 0) > 0
      ? rateText(bucket.number_accuracy)
      : "等待驗證";
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
      "TW_DAILY539",
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
      code: "weekly",
      title: "本週唯一號碼",
      detail: "只定錨1組 · 同週不換號",
    }];
    if (!modes.some((item) => item.code === state.mode)) state.mode = "weekly";
    $("#mode-picker").classList.add("weekly-only");
    $("#mode-picker").innerHTML = modes.map((mode) => `
      <button class="mode ${mode.code === state.mode ? "active" : ""}"
              data-mode="${mode.code}" role="radio"
              aria-checked="${mode.code === state.mode}">
        <strong>${esc(mode.title)}</strong><span>${esc(mode.detail)}</span>
      </button>`).join("");
    $("#star-control").classList.toggle("hidden", game.game_type !== "high_frequency");
  }

  function renderDataStatus() {
    const data = state.dashboard.data;
    const badge = $("#data-badge");
    document.body.dataset.gameType = state.dashboard.game.game_type;
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
    const mode = run.config?.simple_mode || "weekly";
    const anchor = run.recommendation_anchor || run.config?.recommendation_anchor || "";
    const weeklyAnchor = run.config?.weekly_number_anchor || anchor;
    const weeklyKey = run.config?.weekly_key || "本週";
    summary.innerHTML = `
      <div class="summary-top">
        <div><span>適用週別</span><strong>${esc(weeklyKey)}</strong></div>
        <span class="summary-status">${anchor ? "開獎前已定錨" : "尚未定錨"}</span>
      </div>
      <p class="summary-label">${esc(modeLabel(mode))} · 本週固定號碼</p>
      <div class="summary-balls">${balls}</div>
      <div class="summary-foot">
        <span>資料截至 ${esc(run.cutoff_draw_no)}${weeklyAnchor ? ` · 週錨 ${esc(weeklyAnchor.slice(0, 10))}…` : ""}</span>
        <span>唯一 1 組 · 驗證期 ${esc(run.target_draw_no)}</span>
      </div>
      <span class="summary-open weekly-locked">本週固定後不更換</span>`;
  }

  function renderRun(run) {
    state.run = run;
    state.ticketPage = 0;
    renderSummary(run);
    if (!run?.tickets?.length) {
      setCombinationsOpen(false);
      return;
    }
    const mode = run.config?.simple_mode || "weekly";
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
    const periods = state.dashboard.recent_periods || [];
    const historicalReview = state.dashboard.historical_weekly_review || {};
    const historicalWeeks = historicalReview.weeks || [];
    if (state.performanceView === "history" && !historicalWeeks.length) {
      state.performanceView = "live";
    }
    const showingHistory = state.performanceView === "history";
    const summary = (
      showingHistory && historicalReview.summary
        ? historicalReview.summary
        : state.dashboard.performance_summary
    ) || {};
    const recent = summary.recent_10 || {};
    const latestWeek = summary.latest_week || {};
    const overall = summary.overall || {};
    const rows = showingHistory ? historicalWeeks : periods;
    const sampleUnit = showingHistory ? "週" : "期";
    const isHighFrequency = state.dashboard?.game?.game_type === "high_frequency";
    const periodPageSize = window.innerWidth >= 861
      ? 10
      : window.innerHeight <= 700
        ? (showingHistory ? 2 : (isHighFrequency ? 1 : 2))
        : window.innerHeight <= 800
          ? (showingHistory ? 3 : (isHighFrequency ? 2 : 3))
          : 5;
    const periodPageCount = Math.max(1, Math.ceil(rows.length / periodPageSize));
    state.periodPage = Math.min(state.periodPage, periodPageCount - 1);
    const visibleRows = rows.slice(
      state.periodPage * periodPageSize,
      state.periodPage * periodPageSize + periodPageSize,
    );
    $("#performance-kicker").textContent = showingHistory
      ? "步驟 3 · 過去10週定錨回測"
      : "步驟 3 · 定錨後等待開獎";
    $("#performance-title").textContent = showingHistory
      ? "近10週唯一組命中表現"
      : "實戰定錨驗證";
    $("#performance-description").textContent = showingHistory
      ? "每週只用當週開始前的資料定錨1組，再與已開獎號碼核對。"
      : "不混入歷史回放；只有開獎前已鎖定的組合才會計分。";
    $("#recent-metric-title").textContent = showingHistory
      ? "近10週平均號碼命中率"
      : "近10週實戰號碼命中率";
    $("#weekly-metric-title").textContent = "最新一週號碼命中率";
    $("#overall-metric-title").textContent = showingHistory
      ? "累計回測號碼命中率"
      : "累計實戰號碼命中率";
    $("#overall-source-label").textContent = showingHistory
      ? "每週無未來資料回測"
      : "只計開獎後實戰";
    $("#recent-hit-rate").textContent = verifiedAccuracy(recent);
    $("#recent-number-accuracy").textContent = recent.evaluated_runs
      ? rateText(recent.target_hit_rate)
      : "尚無";
    $("#recent-sample-count").textContent = `${recent.evaluated_runs || 0}${sampleUnit}`;
    $("#weekly-hit-rate").textContent = verifiedAccuracy(latestWeek);
    $("#weekly-number-accuracy").textContent = latestWeek.evaluated_runs
      ? rateText(latestWeek.target_hit_rate)
      : "尚無";
    $("#weekly-sample-count").textContent = `${latestWeek.evaluated_runs || 0}${sampleUnit}`;
    $("#latest-week-label").textContent = latestWeek.week || "尚無週資料";
    $("#overall-hit-rate").textContent = verifiedAccuracy(overall);
    $("#overall-sample-count").textContent = `${overall.evaluated_runs || 0}${sampleUnit}`;
    $("#view-live-count").textContent = `${periods.length}期`;
    $("#view-history-count").textContent = `${historicalWeeks.length}週`;
    $("#view-live").classList.toggle("active", !showingHistory);
    $("#view-history").classList.toggle("active", showingHistory);
    $("#weekly-table").innerHTML = showingHistory
      ? visibleRows.map((row) => {
        const predicted = comparisonBalls(row, row.predicted_numbers);
        const actual = comparisonBalls(row, row.actual_numbers);
        const special = comparisonBalls(
          row,
          row.actual_special_numbers,
          { special: true },
        );
        return `<article class="period-card weekly-ball-card">
          <div class="period-id">
            <span>${esc(row.week)} · ${esc(row.sample_draw_date)}</span>
            <strong>
              ${esc(row.sample_draw_no)}
              <small>定錨 ${esc((row.walk_forward_anchor || "").slice(0, 6))}</small>
            </strong>
          </div>
          <div class="compare-group">
            <span>定錨</span><div>${predicted}</div>
          </div>
          <div class="compare-group actual">
            <span>開獎</span><div>${actual}${special ? `<i>＋</i>${special}` : ""}</div>
          </div>
          <div class="period-rate weekly-rate">
            <strong>${rateText(row.number_accuracy)}</strong>
            <small>
              本週中 ${row.target_hit_draws || 0}/${row.evaluated_runs || 0}期 ·
              命中 ${row.sample_hit_count || 0}/${row.sample_number_count || 0}碼
            </small>
          </div>
        </article>`;
      }).join("")
      : visibleRows.map((row) => {
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
            <span>唯一組</span><div>${predicted}</div>
          </div>
          <div class="compare-group actual">
            <span>開獎</span><div>${actual}${special ? `<i>＋</i>${special}` : ""}</div>
          </div>
          <div class="period-rate">
            <strong>${rateText(row.comparison_hit_rate)}</strong>
            <small class="${row.target_achieved ? "target-pass" : "target-miss"}">
              命中 ${row.comparison_hit_count || 0}/${row.comparison_number_count || 0}碼 ·
              定錨 ${esc((row.recommendation_anchor || "").slice(0, 8))}
            </small>
          </div>
        </article>`;
      }).join("");
    const empty = rows.length === 0;
    $("#weekly-empty").textContent = showingHistory
      ? "尚未建立近10週無未來資料回測；完成週更整理後會顯示在這裡。"
      : "目前沒有「先定錨、後開獎」的合格紀錄；等目標期開獎並更新資料後才會開始統計。";
    $("#weekly-empty").classList.toggle("hidden", !empty);
    $("#period-pager").classList.toggle("hidden", periodPageCount <= 1);
    $("#period-page").textContent = `第 ${state.periodPage + 1}／${periodPageCount} 頁`;
    const unit = showingHistory ? "週" : "期";
    $("#period-prev").textContent = `← 前${periodPageSize}${unit}`;
    $("#period-next").textContent = `後${periodPageSize}${unit} →`;
    $("#period-prev").disabled = state.periodPage === 0;
    $("#period-next").disabled = state.periodPage >= periodPageCount - 1;
    $("#metric-note").textContent = showingHistory
      ? historicalReview.note
      : state.dashboard.metric_note;
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
        : `目標 ${record.target_draw_no} · 定錨 ${(record.recommendation_anchor || "").slice(0, 8)}`;
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
    state.mode = "weekly";
    state.run = null;
    state.periodPage = 0;
    state.performanceView = "history";
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
          ticket_count: 1,
          star_count: Number($("#star-count").value),
          refresh,
        }),
      });
      renderRun(run);
      state.dashboard = await api(`/api/simple/dashboard/${encodeURIComponent(state.gameCode)}`);
      renderDataStatus();
      renderWeekly();
      renderHistory();
      notice("本週唯一1組已定錨保存；同週不會換號");
    } catch (error) {
      notice(error.message, true);
    } finally {
      state.busy = false;
      button.disabled = false;
      button.querySelector("span").textContent = "查看本週固定號碼";
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
  $("#view-live").addEventListener("click", () => {
    state.performanceView = "live";
    state.periodPage = 0;
    renderWeekly();
  });
  $("#view-history").addEventListener("click", () => {
    state.performanceView = "history";
    state.periodPage = 0;
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
    if (state.dashboard) renderWeekly();
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
