(() => {
  "use strict";

  const state = { games: [], page: "overview", wizardStep: 1, currentRun: null, drawPage: 1 };
  const titles = {
    overview:"首頁總覽",data:"資料中心",rules:"彩種與規則",draws:"歷史開獎",
    frequency:"冷熱號分析",omission:"遺漏值分析",structure:"號碼結構分析",ac:"AC值分析",
    wizard:"影片五步選號",advanced:"進階自訂選號",records:"推薦紀錄",
    evaluation:"開獎結果核對",replay:"歷史逐期模擬",jobs:"系統工作",settings:"系統設定"
  };

  const $ = (selector, root=document) => root.querySelector(selector);
  const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[char]));

  async function api(url, options={}) {
    const response = await fetch(url, options);
    const type = response.headers.get("content-type") || "";
    const payload = type.includes("json") ? await response.json() : await response.text();
    if (!response.ok) {
      const error = new Error(payload.message || `請求失敗（${response.status}）`);
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function notice(message, error=false) {
    const box = $("#notice");
    box.textContent = message;
    box.classList.toggle("error", error);
    box.classList.remove("hidden");
    clearTimeout(notice.timer);
    notice.timer = setTimeout(() => box.classList.add("hidden"), 6500);
  }

  function showError(error) {
    const detail = error.payload?.detail;
    const suffix = detail?.suggestion ? `；${detail.suggestion}` : "";
    notice(`${error.message}${suffix}`, true);
  }

  function openPage(name) {
    state.page = name;
    $$(".page").forEach(page => page.classList.toggle("active", page.id === `page-${name}`));
    $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.page === name));
    $("#page-title").textContent = titles[name] || name;
    $(".sidebar").classList.remove("open");
    window.scrollTo({top:0, behavior:"smooth"});
    if (name === "overview") loadOverview();
    if (name === "rules") loadRules();
    if (name === "draws") loadDraws();
    if (name === "records") loadRecords();
    if (name === "jobs") loadJobs();
  }

  async function initialize() {
    bindNavigation();
    bindActions();
    try {
      const health = await api("/api/health");
      $("#health-label").textContent = `系統正常 · v${health.version}`;
      state.games = await api("/api/games");
      populateGameSelects();
      await loadOverview();
    } catch (error) {
      $("#health-label").textContent = "系統連線異常";
      showError(error);
    }
  }

  function bindNavigation() {
    $$(".nav-item").forEach(item => item.addEventListener("click", () => openPage(item.dataset.page)));
    $$("[data-open-page]").forEach(item => item.addEventListener("click", () => openPage(item.dataset.openPage)));
    $("#menu-toggle").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
  }

  function bindActions() {
    $$("[data-update]").forEach(button => button.addEventListener("click", () => updateData(button.dataset.update)));
    $("#import-submit").addEventListener("click", uploadImport);
    $("#draw-refresh").addEventListener("click", () => { state.drawPage = 1; loadDraws(); });
    $("#draw-game").addEventListener("change", () => { state.drawPage = 1; loadDraws(); });
    $("#draw-page-size").addEventListener("change", () => { state.drawPage = 1; loadDraws(); });
    $$(".run-analysis").forEach(button => button.addEventListener("click", runAnalysis));
    $$("#wizard-progress button").forEach(button => button.addEventListener("click", () => setWizardStep(+button.dataset.step)));
    $("#wizard-prev").addEventListener("click", () => setWizardStep(state.wizardStep - 1));
    $("#wizard-next").addEventListener("click", nextWizard);
    $("#wizard-game").addEventListener("change", wizardGameChanged);
    $("#generate-button").addEventListener("click", generateTickets);
    $("#lock-run").addEventListener("click", lockCurrentRun);
    $("#records-refresh").addEventListener("click", loadRecords);
    $("#evaluation-submit").addEventListener("click", evaluateRun);
    $("#replay-submit").addEventListener("click", startReplay);
    $("#jobs-refresh").addEventListener("click", loadJobs);
  }

  function populateGameSelects() {
    const options = state.games.map(game =>
      `<option value="${esc(game.game_code)}">${esc(game.display_name)} · ${esc(game.game_code)}</option>`
    ).join("");
    $$(".game-select").forEach(select => {
      select.innerHTML = options;
      if ([...select.options].some(option => option.value === "TW_LOTTO649")) select.value = "TW_LOTTO649";
    });
    const replayAllowed = state.games.filter(game => ["unordered_unique_numbers","derived_game"].includes(game.game_type));
    $("#replay-game").innerHTML = replayAllowed.map(game => `<option value="${esc(game.game_code)}">${esc(game.display_name)}</option>`).join("");
    $("#replay-game").value = "TW_LOTTO649";
  }

  async function loadOverview() {
    try {
      const data = await api("/api/overview");
      const total = data.games.reduce((sum, game) => sum + game.draw_count, 0);
      const available = data.games.filter(game => game.draw_count > 0).length;
      const conflicts = data.games.reduce((sum, game) => sum + game.conflict_count, 0);
      $("#overview-metrics").innerHTML = [
        ["支援彩種", data.games.length, "9種規則已版本化"],
        ["開獎資料", total, "正式與fixture分開標示"],
        ["已有資料彩種", available, `共${data.games.length}種`],
        ["衝突期數", conflicts, conflicts ? "需要人工處理" : "目前無衝突"]
      ].map(item => `<div class="metric"><span>${esc(item[0])}</span><b>${esc(item[1])}</b><small>${esc(item[2])}</small></div>`).join("");
      $("#overview-games").innerHTML = data.games.map(game => `<tr>
        <td>${esc(game.market_code)}</td><td><b>${esc(game.display_name)}</b><br><small>${esc(game.game_code)}</small></td>
        <td>${game.draw_count}</td><td>${esc(game.latest_draw_no || "—")}</td><td>${esc(game.latest_draw_date || "—")}</td>
        <td><span class="status ${game.verification_status?.includes("fixture") ? "fixture" : ""}">${esc(game.verification_status)}</span></td>
      </tr>`).join("");
    } catch (error) { showError(error); }
  }

  async function loadRules() {
    try {
      state.games = await api("/api/games");
      $("#rules-grid").innerHTML = state.games.map(game => {
        const rules = game.ruleset;
        const pools = rules?.config?.pools || [];
        return `<article class="rule-card">
          <header><div><span class="rule-code">${esc(game.game_code)}</span><h3>${esc(game.display_name)}</h3></div>
          <span class="status ${rules?.verified ? "" : "warn"}">${rules?.verified ? "已驗證範圍" : "待人工確認"}</span></header>
          <p>${esc(game.game_type)}${game.parent_game_code ? ` · 底層${esc(game.parent_game_code)}` : ""}</p>
          ${pools.map(pool => `<div class="rule-pool"><b>${esc(pool.label)}</b> · ${pool.min}～${pool.max}，開出${pool.draw_count}，單式選${pool.pick_count}</div>`).join("")}
          <p>${esc(rules?.config?.verified_scope || "")}</p>
        </article>`;
      }).join("");
    } catch (error) { showError(error); }
  }

  async function loadDraws() {
    try {
      const game = $("#draw-game").value || "TW_LOTTO649";
      const size = +$("#draw-page-size").value || 50;
      const data = await api(`/api/draws?game_code=${encodeURIComponent(game)}&page=${state.drawPage}&page_size=${size}`);
      $("#draw-table").innerHTML = data.items.map(draw => {
        const entries = Object.entries(draw.pools);
        const primary = entries[0]?.[1] || [];
        const secondary = entries.slice(1).map(([name,numbers]) => `${name}：${numbers.map(two).join(" ")}`).join("；");
        const extras = [secondary, draw.special_numbers.length ? `特別號：${draw.special_numbers.map(two).join(" ")}` : ""].filter(Boolean).join("；");
        return `<tr><td><b>${esc(draw.draw_no)}</b></td><td>${esc(draw.draw_date)}</td><td>${primary.map(ball).join("")}</td><td>${esc(extras || "—")}</td><td>${esc(draw.source_status)}</td><td><span class="status fixture">${esc(draw.verification_status)}</span></td></tr>`;
      }).join("") || `<tr><td colspan="6">尚無資料</td></tr>`;
      $("#draw-pagination").innerHTML = `<button ${data.page <= 1 ? "disabled" : ""} data-page="${data.page-1}">上一頁</button><span>第 ${data.page} / ${Math.max(1,data.pages)} 頁，共 ${data.total} 期</span><button ${data.page >= data.pages ? "disabled" : ""} data-page="${data.page+1}">下一頁</button>`;
      $$("#draw-pagination button").forEach(button => button.addEventListener("click", () => { state.drawPage=+button.dataset.page; loadDraws(); }));
    } catch (error) { showError(error); }
  }

  function two(value) { return String(value).padStart(2,"0"); }
  function ball(value) { return `<span class="number-ball">${esc(two(value))}</span>`; }

  async function runAnalysis(event) {
    const section = event.target.closest(".analysis-page");
    const kind = event.target.dataset.kind;
    const game = $(".analysis-game", section).value;
    const lookback = +$(".analysis-lookback", section).value;
    try {
      const data = await api(`/api/analytics/${kind}?game_code=${encodeURIComponent(game)}&lookback_count=${lookback}`);
      if (kind === "frequency") renderFrequency(section, data);
      if (kind === "omission") renderOmission(section, data);
      if (kind === "structure" || kind === "ac") renderStructure(section, data);
    } catch (error) { showError(error); }
  }

  function renderFrequency(section, data) {
    $(".analysis-summary", section).innerHTML = `<div class="info-strip">資料截止 ${esc(data.cutoff_draw_no)}（${esc(data.cutoff_draw_date)}）；實際使用 ${data.actual_lookback} 期；狀態 ${esc(data.verification_status)}</div>`;
    const pools = Object.values(data.pools);
    $(".analysis-balls", section).innerHTML = pools.map(pool => pool.metrics.map(metric =>
      `<div class="ball-stat ${tempClass(metric.temperature)}"><b>${two(metric.number)}</b><small>${esc(metric.temperature)} · ${metric.frequency}次<br>遺漏 ${metric.current_omission}</small></div>`
    ).join("")).join("");
  }

  function renderOmission(section, data) {
    $(".analysis-summary", section).innerHTML = `<div class="info-strip">資料截止 ${esc(data.cutoff_draw_no)}；實際使用 ${data.actual_lookback} 期。</div>`;
    const metrics = Object.values(data.pools).flatMap(pool => pool.metrics);
    $(".omission-table", section).innerHTML = metrics.map(metric => `<tr><td>${ball(metric.number)}</td><td><b>${metric.current_omission}</b></td><td>${metric.frequency}</td><td>${metric.average_gap ?? "—"}</td><td>${metric.maximum_gap ?? "—"}</td><td>${esc(metric.last_seen_draw_no || "從未出現")}</td><td>${esc(metric.temperature)}</td></tr>`).join("");
  }

  function renderStructure(section, data) {
    const target = $(".structure-charts", section);
    if ($(".analysis-summary", section)) $(".analysis-summary", section).innerHTML = data.message ? `<div class="info-strip">${esc(data.message)}</div>` : "";
    target.innerHTML = Object.entries(data.distributions).map(([key, distribution]) => {
      const entries = Object.entries(distribution);
      const max = Math.max(1, ...entries.map(entry => +entry[1]));
      return `<div class="mini-chart"><h3>${esc(metricName(key))}</h3>${entries.slice(0,35).map(([label,count]) => `<div class="bar-row"><span>${esc(label)}</span><div class="bar"><i style="width:${(+count/max)*100}%"></i></div><b>${count}</b></div>`).join("")}</div>`;
    }).join("");
  }

  const metricName = key => ({odd_count:"奇數個數",high_count:"大號個數",sum:"和值",span:"跨度",consecutive_pairs:"連號對數",ac:"AC值"}[key] || key);
  const tempClass = value => value === "熱" ? "hot" : value === "冷" ? "cold" : "warm";

  async function nextWizard() {
    if (state.wizardStep === 1) {
      try {
        const game = $("#wizard-game").value, lookback = +$("#wizard-lookback").value;
        const data = await api(`/api/analytics/frequency?game_code=${encodeURIComponent(game)}&lookback_count=${lookback}`);
        $("#wizard-data-summary").textContent = `資料截止 ${data.cutoff_draw_no}（${data.cutoff_draw_date}），實際使用 ${data.actual_lookback} 期；資料狀態：${data.verification_status}。`;
        $("#wizard-balls").innerHTML = Object.values(data.pools).flatMap(pool => pool.metrics).map(metric => `<div class="ball-stat ${tempClass(metric.temperature)}"><b>${two(metric.number)}</b><small>${metric.temperature} · 遺漏${metric.current_omission}</small></div>`).join("");
      } catch (error) { showError(error); return; }
    }
    setWizardStep(Math.min(5, state.wizardStep + 1));
  }

  function setWizardStep(step) {
    state.wizardStep = Math.max(1, Math.min(5, step));
    $$("#wizard-progress button").forEach(button => button.classList.toggle("active", +button.dataset.step === state.wizardStep));
    $$(".wizard-step").forEach(panel => panel.classList.toggle("active", +panel.dataset.stepPanel === state.wizardStep));
    $("#wizard-prev").disabled = state.wizardStep === 1;
    $("#wizard-next").classList.toggle("hidden", state.wizardStep === 5);
  }

  function wizardGameChanged() {
    const game = state.games.find(item => item.game_code === $("#wizard-game").value);
    const count = game?.ruleset?.config?.pools?.[0]?.pick_count || 6;
    $("#wizard-odd").value = count === 5 ? "2,3" : count === 6 ? "2,3,4" : "";
    $("#wizard-high").value = $("#wizard-odd").value;
    $("#wizard-overlap").value = count === 5 ? 2 : count === 6 ? 3 : Math.floor(count/2);
    $("#star-label").classList.toggle("hidden", game?.game_type !== "high_frequency");
    $("#wizard-ac-note").textContent = game?.supports_ac
      ? "留空時使用該彩種最近最多100期AC分布的第20至第80百分位。"
      : "此遊戲不使用AC值，系統改採位置、和值、奇偶、大小與重複型態等數字結構。";
  }

  function intList(selector) {
    const text = $(selector).value.trim();
    return text ? text.split(/[,，\s]+/).filter(Boolean).map(Number) : [];
  }

  async function generateTickets() {
    const payload = {
      game_code: $("#wizard-game").value,
      ticket_count: +$("#wizard-count").value,
      lookback_count: +$("#wizard-lookback").value,
      random_seed: +$("#wizard-seed").value,
      preset_code: $("#wizard-preset").value,
      target_draw_no: $("#wizard-target").value.trim() || null,
      max_overlap: +$("#wizard-overlap").value,
      star_count: +$("#wizard-star").value,
      include_numbers: intList("#wizard-include"),
      exclude_numbers: intList("#wizard-exclude"),
      allowed_odd_counts: intList("#wizard-odd").length ? intList("#wizard-odd") : null,
      allowed_high_counts: intList("#wizard-high").length ? intList("#wizard-high") : null,
      ac_min: $("#wizard-ac-min").value === "" ? null : +$("#wizard-ac-min").value,
      ac_max: $("#wizard-ac-max").value === "" ? null : +$("#wizard-ac-max").value
    };
    const button = $("#generate-button");
    button.disabled = true; button.textContent = "正在產生與差異化挑選…";
    try {
      state.currentRun = await api("/api/generation/run", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      renderRun(state.currentRun);
      notice(`已產生 ${state.currentRun.generated_ticket_count} 組，seed ${state.currentRun.random_seed}`);
    } catch (error) { showError(error); }
    finally { button.disabled=false; button.innerHTML='產生條件式組合 <span>→</span>'; }
  }

  function renderRun(run) {
    $("#generation-results").classList.remove("hidden");
    $("#run-meta").textContent = `${run.game_name} · 目標 ${run.target_draw_no} · 截止 ${run.cutoff_draw_no} · seed ${run.random_seed}`;
    $("#ticket-grid").innerHTML = run.tickets.map(ticket => {
      const poolHtml = Object.entries(ticket.pools).map(([name,numbers], index) => `${index ? `<span class="pool-divider">${esc(name)}</span>` : ""}<div class="ticket-balls">${numbers.map(ball).join("")}</div>`).join("");
      const structure = ticket.explanation.structure;
      return `<article class="ticket-card"><div class="ticket-index">${ticket.ticket_index}</div><div>${poolHtml}<div class="ticket-meta"><span>偏好 ${ticket.preference_score.toFixed(3)}</span><span>差異 ${ticket.diversity_score.toFixed(3)}</span><span>奇 ${structure.odd_count ?? "—"}</span><span>大 ${structure.high_count ?? "—"}</span><span>和值 ${structure.sum}</span><span>AC ${structure.ac ?? "不適用"}</span></div><p class="ticket-message">${esc(ticket.explanation.message)}</p></div></article>`;
    }).join("");
    const base = `/api/exports/generation/${run.run_uuid}`;
    $("#export-csv").href = `${base}.csv`; $("#export-json").href = `${base}.json`; $("#export-txt").href = `${base}.txt`;
    $("#lock-run").disabled = run.locked;
    $("#lock-run").textContent = run.locked ? "已鎖定" : "鎖定本次推薦";
    $("#generation-results").scrollIntoView({behavior:"smooth",block:"start"});
  }

  async function lockCurrentRun() {
    if (!state.currentRun) return;
    try {
      state.currentRun = await api(`/api/generation/runs/${state.currentRun.run_uuid}/lock`, {method:"POST"});
      renderRun(state.currentRun); notice("推薦紀錄已鎖定，原紀錄將保持不變。");
    } catch (error) { showError(error); }
  }

  async function loadRecords() {
    try {
      const records = await api("/api/generation/runs?limit=100");
      $("#records-list").innerHTML = records.map(run => `<article class="record"><div><span class="status ${run.locked ? "" : "fixture"}">${run.locked ? "已鎖定" : "未鎖定"}</span><h3>${esc(run.game_name)} · 目標 ${esc(run.target_draw_no)}</h3><p>截止 ${esc(run.cutoff_draw_no)} · ${esc(run.preset_name)} · seed ${run.random_seed} · ${run.generated_ticket_count}組</p><code>${esc(run.run_uuid)}</code></div><div class="record-actions"><button class="ghost view-run" data-run="${esc(run.run_uuid)}">查看</button><a class="ghost button-link" href="/api/exports/generation/${esc(run.run_uuid)}.csv">CSV</a></div></article>`).join("") || "<div class='panel'>尚無推薦紀錄</div>";
      $$(".view-run").forEach(button => button.addEventListener("click", async () => {
        try { state.currentRun = await api(`/api/generation/runs/${button.dataset.run}`); openPage("wizard"); renderRun(state.currentRun); }
        catch (error) { showError(error); }
      }));
    } catch (error) { showError(error); }
  }

  async function evaluateRun() {
    const run = $("#evaluation-run").value.trim(), draw = $("#evaluation-draw").value.trim();
    if (!run) return notice("請輸入推薦run UUID", true);
    try {
      const url = `/api/generation/runs/${encodeURIComponent(run)}/evaluate${draw ? `?actual_draw_no=${encodeURIComponent(draw)}` : ""}`;
      const result = await api(url, {method:"POST"});
      $("#evaluation-output").textContent = JSON.stringify(result,null,2);
    } catch (error) { showError(error); }
  }

  async function startReplay() {
    const payload = {
      game_code:$("#replay-game").value,start_index:+$("#replay-start").value,
      end_index:+$("#replay-end").value,lookback_count:+$("#replay-lookback").value,
      tickets_per_draw:+$("#replay-tickets").value,random_seed:+$("#replay-seed").value,
      baseline_repetitions:20
    };
    try {
      const result = await api("/api/replay/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      $("#replay-progress").classList.remove("hidden"); pollReplay(result.run_uuid);
    } catch (error) { showError(error); }
  }

  async function pollReplay(runUuid) {
    try {
      const result = await api(`/api/replay/${runUuid}`);
      const ratio = result.progress_total ? result.progress_current/result.progress_total*100 : 0;
      $("#replay-progress span").style.width = `${ratio}%`;
      $("#replay-progress p").textContent = `${result.status} · ${result.progress_current}/${result.progress_total}`;
      if (["pending","running"].includes(result.status)) return setTimeout(() => pollReplay(runUuid),1000);
      $("#replay-output").textContent = JSON.stringify(result,null,2);
      notice(result.status === "completed" ? "歷史逐期模擬完成" : `模擬狀態：${result.status}`, result.status !== "completed");
    } catch (error) { showError(error); }
  }

  async function updateData(scope) {
    try {
      const result = await api(`/api/data/update?scope=${encodeURIComponent(scope)}`,{method:"POST"});
      notice(`官方資料檢查已建立，工作編號 ${result.job_uuid}`); openPage("jobs");
      setTimeout(loadJobs,600);
    } catch (error) { showError(error); }
  }

  async function uploadImport() {
    const file = $("#import-file").files[0];
    if (!file) return notice("請先選擇CSV或Excel檔案", true);
    const form = new FormData(); form.append("file",file);
    try {
      const result = await api("/api/imports/upload",{method:"POST",body:form});
      notice(`匯入完成：新增 ${result.summary.inserted} 期，略過 ${result.summary.skipped} 期，衝突 ${result.summary.conflicts} 期`);
      loadOverview();
    } catch (error) { showError(error); }
  }

  async function loadJobs() {
    try {
      const jobs = await api("/api/jobs");
      $("#jobs-list").innerHTML = jobs.map(job => `<article class="record"><div><span class="status ${["failed","cancelled","interrupted"].includes(job.status) ? "warn" : ""}">${esc(job.status)}</span><h3>${esc(job.job_type)}</h3><p>${esc(job.message)} · ${job.progress_current}/${job.progress_total}</p><code>${esc(job.job_uuid)}</code>${job.result ? `<pre class="json-output">${esc(JSON.stringify(job.result,null,2))}</pre>` : ""}</div><div class="record-actions">${["pending","running"].includes(job.status) ? `<button class="ghost cancel-job" data-job="${esc(job.job_uuid)}">取消</button>` : ""}</div></article>`).join("") || "<div class='panel'>尚無系統工作</div>";
      $$(".cancel-job").forEach(button => button.addEventListener("click", async () => {
        try { await api(`/api/jobs/${button.dataset.job}/cancel`,{method:"POST"}); loadJobs(); } catch(error){showError(error);}
      }));
      if (jobs.some(job => ["pending","running"].includes(job.status)) && state.page === "jobs") setTimeout(loadJobs,1500);
    } catch (error) { showError(error); }
  }

  initialize();
})();

