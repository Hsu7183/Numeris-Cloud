"use strict";

window.NumerisDrawFeed = (() => {
  // Use the same published GitHub snapshot from FastAPI and GitHub Pages.
  const base = "https://raw.githubusercontent.com/Hsu7183/Numeris-Cloud/main/docs/data/";
  const options = {
    daily539: { file: "539-workbench.json", size: 5, max: 39 },
    lotto649: { file: "lotto649.json", size: 6, max: 49 },
  };
  const formatBall = (ball) => String(ball).padStart(2, "0");

  async function fetchDraws(game) {
    const { file, size, max } = options[game];
    const response = await fetch(base + file, {
      cache: "no-store",
      signal: AbortSignal.timeout(12000),
    });
    if (!response.ok) throw new Error(`資料服務回傳 ${response.status}`);
    const { draws } = await response.json();
    if (!Array.isArray(draws) || !draws.length || new Set(draws.map(row => row.draw_no)).size !== draws.length ||
        draws.some(({ draw_no, draw_date, numbers, special_numbers }) =>
          !/^\d{9}$/.test(draw_no) || !/^\d{4}-\d{2}-\d{2}$/.test(draw_date) ||
          !Array.isArray(numbers) || numbers.length !== size || new Set(numbers).size !== size ||
          numbers.some(ball => !Number.isInteger(ball) || ball < 1 || ball > max) ||
          (game === "lotto649" && (!Array.isArray(special_numbers) || special_numbers.length !== 1 ||
            !Number.isInteger(special_numbers[0]) || special_numbers[0] < 1 ||
            special_numbers[0] > max || numbers.includes(special_numbers[0]))))) {
      throw new Error("開獎資料格式不符");
    }
    return draws.sort((a, b) => b.draw_date.localeCompare(a.draw_date) || b.draw_no.localeCompare(a.draw_no));
  }

  function watch(game, render) {
    const status = document.getElementById("draw-feed-status");
    let snapshot = "";
    let latest;
    async function refresh() {
      let draws;
      try {
        draws = await fetchDraws(game);
      } catch (error) {
        status.dataset.error = "";
        status.textContent = latest
          ? `暫時無法同步，顯示已載入的資料（截至 ${latest.draw_date}，第 ${latest.draw_no} 期）`
          : "暫時無法取得開獎資料，稍後會自動重試。";
        if (!snapshot) {
          snapshot = "[]";
          render([]);
        }
        return;
      }
      latest = draws[0];
      delete status.dataset.error;
      status.textContent = `官方資料｜截至 ${latest.draw_date}（第 ${latest.draw_no} 期）・共 ${draws.length} 期`;
      const next = JSON.stringify(draws);
      if (next !== snapshot) {
        snapshot = next;
        render(draws);
      }
    }

    async function poll() {
      try {
        await refresh();
      } finally {
        setTimeout(poll, 300000);
      }
    }
    void poll();
  }

  function workbenchRows(draws) {
    return draws.slice().reverse().map(row => [
      row.draw_no, row.draw_date, row.numbers.map(formatBall).join(" "),
    ]);
  }

  return { watch, workbenchRows, formatBall };
})();
