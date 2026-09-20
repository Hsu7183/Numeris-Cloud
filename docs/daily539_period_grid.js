(() => {
  "use strict";
  const config = [
    { period: 20, columns: 12 },
    { period: 50, columns: 10 },
    { period: 100, columns: 9 },
    { period: 200, columns: 9 },
  ];
  const list = document.querySelector("#period-grid-list");
  const meta = document.querySelector("#grid-meta");
  const winningDraws = document.querySelector("#winning-draws");
  const params = new URLSearchParams(window.location.search);
  const dateFrom = params.get("from");
  const dateTo = params.get("to");

  async function loadData() {
    if (!dateFrom || !dateTo) {
      const payload = JSON.parse(localStorage.getItem("daily539OutputData") || "null");
      return {
        draws: payload?.draws || [],
        markerDraws: (payload?.draws || []).slice(0, 27),
        markerName: "近 27 期",
        latestDrawNo: payload?.latest_draw_no,
        latestDrawDate: payload?.latest_draw_date,
        historical: false,
      };
    }

    const response = await fetch(`/api/draws?game_code=TW_DAILY539&date_to=${encodeURIComponent(dateTo)}&page_size=200`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "指定期間資料無法取得");
    const draws = result.items.map((item) => ({
      draw_no: item.draw_no,
      draw_date: item.draw_date,
      numbers: (item.pools?.main || []).slice().sort((first, second) => first - second),
    }));
    const markerDraws = draws.filter((draw) => draw.draw_date >= dateFrom && draw.draw_date <= dateTo);
    return {
      draws,
      markerDraws,
      markerName: "112/06/26–112/07/18",
      latestDrawNo: draws[0]?.draw_no,
      latestDrawDate: draws[0]?.draw_date,
      historical: true,
    };
  }

  function frequencyGroups(draws, period) {
    const counts = new Map(Array.from({ length: 39 }, (_, index) => [index + 1, 0]));
    draws.slice(0, period).forEach((draw) => {
      draw.numbers.forEach((number) => counts.set(number, counts.get(number) + 1));
    });
    const groups = new Map();
    counts.forEach((count, number) => {
      const numbers = groups.get(count) || [];
      numbers.push(number);
      groups.set(count, numbers);
    });
    return groups;
  }

  function buildGrid({ period, columns }, draws, markerOccurrences, markerName) {
    const groups = frequencyGroups(draws, period);
    const columnHeadings = Array.from({ length: columns }, (_, index) => `<th>${index + 1}</th>`).join("");
    const bottomWatermarks = Array.from({ length: columns }, (_, index) => `<td>${index + 1}</td>`).join("");
    const rows = Array.from({ length: 43 }, (_, rowIndex) => {
      const count = 42 - rowIndex;
      const numbers = groups.get(count) || [];
      const cells = Array.from({ length: columns }, (_, columnIndex) => {
        const number = numbers[columnIndex];
        const occurrences = markerOccurrences.get(number) || 0;
        const marked = occurrences > 0;
        const repeatLabel = occurrences === 1 ? "" : String(occurrences - 1);
        const ball = `<span class="grid-ball recent-ball" title="${String(number).padStart(2, "0")}號：${markerName}共出現 ${occurrences} 次" aria-label="${String(number).padStart(2, "0")}號：${markerName}共出現 ${occurrences} 次">${repeatLabel}</span>`;
        return `<td${marked ? ' class="winning-number"' : ""}><span class="cell-watermark">${columnIndex + 1}</span>${marked ? ball : ""}</td>`;
      }).join("");
      return `<tr><th scope="row">${String(count).padStart(2, "0")}</th>${cells}</tr>`;
    }).join("");
    return `<section class="period-panel">
      <header><strong>${period}</strong><span>期</span><small>每行 ${columns} 格 · 共 43 行</small></header>
      <div class="table-frame"><table aria-label="${period} 期格表"><thead><tr><th>行</th>${columnHeadings}</tr></thead><tbody>${rows}</tbody><tfoot><tr><th>格</th>${bottomWatermarks}</tr></tfoot></table></div>
    </section>`;
  }

  async function render() {
    const data = await loadData();
    if (!data.draws.length) throw new Error("沒有可計算的開獎資料");
    const markerOccurrences = new Map();
    data.markerDraws.forEach((draw) => draw.numbers.forEach((number) => {
      markerOccurrences.set(number, (markerOccurrences.get(number) || 0) + 1);
    }));
    list.innerHTML = config.map((item) => buildGrid(item, data.draws, markerOccurrences, data.markerName)).join("");
    meta.textContent = `${data.markerName} · 共 ${data.markerDraws.length} 期 · 計算終點：${data.latestDrawNo}期 · ${data.latestDrawDate}`;
    if (data.historical) {
      const toRocDate = (value) => {
        const [year, month, day] = value.split("-").map(Number);
        return `${year - 1911}/${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}`;
      };
      winningDraws.innerHTML = `<h2>20 期中獎號碼</h2><div class="winning-draw-list">${data.markerDraws.map((draw, index) => `
        <article><strong>${String(index + 1).padStart(2, "0")}</strong><span>${toRocDate(draw.draw_date)} · ${draw.draw_no}期</span><b>${draw.numbers.map((number) => String(number).padStart(2, "0")).join("　")}</b></article>
      `).join("")}</div>`;
      winningDraws.classList.remove("hidden");
    }
  }

  render().catch((error) => {
    list.innerHTML = `<p class="grid-error">${error.message || "格表資料無法載入"}</p>`;
  });
})();
