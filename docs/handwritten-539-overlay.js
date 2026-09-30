(() => {
  "use strict";
  const rangeDays = [6, 12, 18];
  const status = document.querySelector("#overlay-status");
  const source = document.querySelector("#overlay-source");
  document.querySelector("#today-date").textContent = `畫面日期：${new Intl.DateTimeFormat("zh-TW", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", weekday: "long" }).format(new Date())}`;
  let loadedDataVersion = "";

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

  const renderPanel = (days, dates, dailyCells) => {
    const selectedDates = dates.slice(-days);
    const label = `${selectedDates[0].replaceAll("-", "/")}～${selectedDates.at(-1).replaceAll("-", "/")}`;
    const counts = new Map();
    dailyCells.slice(-days).flat().forEach((key) => counts.set(key, (counts.get(key) || 0) + 1));
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
    return `<section class="overlay-panel"><header><strong>${days} 天疊加</strong><span>${label}</span></header><table><thead><tr><th>次數</th>${headers}</tr></thead><tbody>${rows}</tbody></table><p class="overlay-note">共 ${days} 個開獎日；紅圈內數字為該框格累計出現次數。</p></section>`;
  };

  async function load() {
    try {
      const response = await fetch(`data/daily539.json?load=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error("開獎資料讀取失敗");
      const payload = await response.json();
      const dates = (payload.draws || []).slice(0, 18).map((draw) => draw.draw_date).reverse();
      if (dates.length < 18) throw new Error("不足 18 個開獎日資料");
      status.textContent = `正在載入最新 18 個開獎日（截至 ${dates.at(-1)}）…`;
      const dailyCells = await Promise.all(dates.map(loadMappedCells));
      document.querySelector("#overlay-panels").innerHTML = rangeDays.map((days) => renderPanel(days, dates, dailyCells)).join("");
      const adjacentDate = dates.at(-1);
      document.querySelector("#adjacent-table").innerHTML = await loadAdjacentTable(adjacentDate);
      document.querySelector("#adjacent-date").textContent = `${adjacentDate.replaceAll("-", "/")} 本期相鄰`;
      document.querySelector(".overlay-header span").textContent = `依最新 18 個實際開獎日累加紅圈位置（截至 ${adjacentDate}）`;
      status.textContent = `已更新至 ${adjacentDate} · 6、12、18 個開獎日疊加 · 每日自動更新已開啟。`;
      enableAutomaticUpdates();
    } catch (error) {
      status.textContent = `疊加資料載入失敗：${error.message}`;
    }
  }
  load();
})();
