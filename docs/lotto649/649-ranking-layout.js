(() => {
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = new URL("649-ranking-layout.css?v=1", document.currentScript.src).href;
  document.head.appendChild(css);
  function arrange() {
    document.querySelectorAll("#numbers.row .cell, .compact-hit-ranking td, #latest-ranking td, #position-hits td").forEach((cell) => {
      if (cell.dataset.rankLayout) return;
      const ball = cell.querySelector(".ball, b, .position-ball");
      const value = cell.querySelector(".count, .hits, .position-hit-count") || cell.querySelector("small");
      if (!ball || !value || ball === value) return;
      cell.dataset.rankLayout = "1";
      cell.classList.add("ranking-layout-cell");
      ball.classList.add("ranking-layout-ball");
      value.classList.add("ranking-layout-value");
      let rank = cell.querySelector("small");
      if (rank === value) rank = null;
      if (!rank) { rank = document.createElement("span"); rank.textContent = String([...cell.parentElement.children].indexOf(cell) + 1); cell.appendChild(rank); }
      rank.classList.add("ranking-layout-rank");
    });
  }
  arrange();
  new MutationObserver(arrange).observe(document.body, { childList: true, subtree: true });
})();
