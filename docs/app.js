(() => {
  "use strict";

  const status = document.querySelector("#status");
  const results = document.querySelector("#results");
  const ball = (number, drawn) => `<span class="ball ${drawn.has(number) ? "drawn-ball" : ""}">${String(number).padStart(2, "0")}</span>`;

  function summarize(draws) {
    const values = Array.from({ length: 39 }, (_, index) => ({ number: index + 1, count: 0 }));
    draws.forEach((draw) => draw.numbers.forEach((number) => { values[number - 1].count += 1; }));
    return values.sort((first, second) => second.count - first.count || first.number - second.number);
  }

  function panel(limit, draws, drawn, suffix = "") {
    const groups = new Map();
    summarize(draws.slice(0, limit)).filter((item) => item.count > 0).forEach((item) => {
      const items = groups.get(item.count) || [];
      items.push(item.number);
      groups.set(item.count, items);
    });
    return `<section class="comparison-panel"><header><p>最近</p><h2>${limit}${suffix}<small>期</small></h2><span>共 ${Math.min(limit, draws.length)} 期</span></header><p class="group-note">同一次數的球號併列</p><div class="frequency-groups">${[...groups.entries()].map(([count, numbers]) => `<article class="frequency-group"><strong>${count}<small>次</small></strong><div>${numbers.map((number) => ball(number, drawn)).join("")}</div></article>`).join("")}</div></section>`;
  }

  function render(payload) {
    const drawn = new Set(payload.draws[0].numbers);
    document.querySelector("#latest-draw").textContent = `${payload.latest_draw_no}期 · ${payload.latest_draw_date}`;
    document.querySelector("#comparison-list").innerHTML = [20, 50, 100, 200].map((limit) => panel(limit, payload.draws, drawn)).join("");
    status.textContent = `已取得 ${payload.draw_count} 期資料 · 更新時間：${new Date(payload.generated_at).toLocaleString("zh-TW")}`;
    results.classList.remove("hidden");
  }

  fetch("data/daily539.json", { cache: "no-store" })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error("尚未建立資料。請在 GitHub Actions 執行更新。")))
    .then(render)
    .catch((error) => { status.textContent = error.message; status.classList.add("error"); });
})();
