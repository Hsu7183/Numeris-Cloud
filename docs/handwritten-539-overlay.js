(() => {
  "use strict";
  const rangeDays = [6, 12, 18];
  const status = document.querySelector("#overlay-status");
  const source = document.querySelector("#overlay-source");
  document.querySelector("#today-date").textContent = `畫面日期：${new Intl.DateTimeFormat("zh-TW", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", weekday: "long" }).format(new Date())}`;
  let loadedDataVersion = "";

  const taipeiDateString = () => {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
    return `${values.year}-${values.month}-${values.day}`;
  };
  const shiftDate = (date, amount) => {
    const value = new Date(`${date}T00:00:00Z`);
    value.setUTCDate(value.getUTCDate() + amount);
    return value.toISOString().slice(0, 10);
  };

  const readDataVersion = async () => {
    const response = await fetch(`data/daily539.json?check=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("無法檢查最新資料");
    const payload = await response.json();
    return `${payload.latest_draw_date || ""}|${payload.generated_at || ""}`;
  };

  const enableAutomaticUpdates = async () => {
    try {
      loadedDataVersion = await readDataVersion();
    } catch (_) {
      // 初次檢查失敗不影響目前已載入的格表。
    }
    const checkForUpdate = async () => {
      try {
        const latestVersion = await readDataVersion();
        if (loadedDataVersion && latestVersion !== loadedDataVersion) {
          location.reload();
          return;
        }
        loadedDataVersion = latestVersion;
      } catch (_) {
        // 保留目前畫面，下一輪再檢查。
      }
    };
    window.setInterval(checkForUpdate, 5 * 60 * 1000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) checkForUpdate();
    });
    window.addEventListener("focus", checkForUpdate);
  };

  const loadMappedCells = (date) => new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    const timeout = window.setTimeout(() => {
      frame.remove();
      reject(new Error(`${date} 載入逾時`));
    }, 30000);
    frame.addEventListener("load", () => {
      const check = window.setInterval(() => {
        const documentRef = frame.contentDocument;
        const ready = documentRef?.querySelector("#sheet-status")?.textContent.startsWith("指定期別");
        if (!ready) return;
        window.clearInterval(check);
        window.clearTimeout(timeout);
        const cells = [...documentRef.querySelectorAll("#number-grid tbody tr")].flatMap((row) => {
          const rowLabel = row.querySelector("th")?.textContent;
          return [...row.querySelectorAll("td")]
            .map((cell, index) => cell.querySelector(".circle") ? `${rowLabel}:${index + 1}` : null)
            .filter(Boolean);
        });
        frame.remove();
        resolve(cells);
      }, 30);
    }, { once: true });
    frame.src = `handwritten-539-grid.html?date=${date}`;
    source.appendChild(frame);
  });

  const loadAdjacentTable = (date) => new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    const timeout = window.setTimeout(() => {
      frame.remove();
      reject(new Error(`${date} 相鄰表格載入逾時`));
    }, 30000);
    frame.addEventListener("load", () => {
      const check = window.setInterval(() => {
        const documentRef = frame.contentDocument;
        const ready = documentRef?.querySelector("#sheet-status")?.textContent.startsWith("指定期別");
        const table = documentRef?.querySelector("#draw-grid");
        if (!ready || !table?.innerHTML) return;
        window.clearInterval(check);
        window.clearTimeout(timeout);
        const html = table.outerHTML;
        frame.remove();
        resolve(html);
      }, 30);
    }, { once: true });
    frame.src = `handwritten-539-grid.html?date=${date}`;
    source.appendChild(frame);
  });

  const renderPanel = (days, endDate, datedCells) => {
    const startDate = shiftDate(endDate, -(days - 1));
    const selected = datedCells.filter(({ date }) => date >= startDate && date <= endDate);
    const label = `${startDate.replaceAll("-", "/")}～${endDate.replaceAll("-", "/")}`;
    const counts = new Map();
    selected.flatMap(({ cells }) => cells).forEach((key) => counts.set(key, (counts.get(key) || 0) + 1));
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = [4, 3, 2, 1, 0].map((rowLabel) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const column = index + 1;
        const count = counts.get(`${rowLabel}:${column}`) || 0;
        const watermark = rowLabel === 3 || rowLabel === 1
          ? `<span style="color:#cfd6d1;font-family:Georgia,serif;font-size:.8rem;font-weight:700">${column}</span>`
          : "";
        const circle = count
          ? `<span class="overlay-circle" style="position:absolute;inset:4px;margin:auto">${count}</span>`
          : "";
        return `<td style="position:relative">${watermark}${circle}</td>`;
      }).join("");
      return `<tr><th>${rowLabel}</th>${cells}</tr>`;
    }).join("");
    return `<section class="overlay-panel"><header><strong>近 ${days} 日疊加</strong><span>${label}</span></header><table><thead><tr><th>次數</th>${headers}</tr></thead><tbody>${rows}</tbody></table><p class="overlay-note">近 ${days} 個日曆日內共有 ${selected.length} 個開獎日；紅圈內數字為累計出現次數。</p></section>`;
  };

  async function load() {
    try {
      const response = await fetch(`data/daily539.json?load=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error("開獎資料讀取失敗");
      const payload = await response.json();
      const endDate = taipeiDateString();
      const startDate = shiftDate(endDate, -17);
      const dates = (payload.draws || []).map((draw) => draw.draw_date)
        .filter((date) => date >= startDate && date <= endDate).reverse();
      if (!dates.length) throw new Error("近 18 日沒有開獎資料");
      status.textContent = `正在載入近 18 日資料（${startDate}～${endDate}）…`;
      const dailyCells = await Promise.all(dates.map(loadMappedCells));
      const datedCells = dates.map((date, index) => ({ date, cells: dailyCells[index] }));
      document.querySelector("#overlay-panels").innerHTML = rangeDays.map((days) => renderPanel(days, endDate, datedCells)).join("");
      const adjacentDate = dates.at(-1);
      document.querySelector("#adjacent-table").innerHTML = await loadAdjacentTable(adjacentDate);
      document.querySelector("#adjacent-date").textContent = `${adjacentDate.replaceAll("-", "/")} 本期相鄰`;
      document.querySelector(".overlay-header span").textContent = `依近 6／12／18 個日曆日累加紅圈位置（截至 ${endDate}）`;
      status.textContent = `已計算至 ${endDate} · 最新開獎資料 ${adjacentDate} · 每日自動更新已開啟。`;
      enableAutomaticUpdates();
    } catch (error) {
      status.textContent = `疊加資料載入失敗：${error.message}`;
    }
  }
  load();
})();
