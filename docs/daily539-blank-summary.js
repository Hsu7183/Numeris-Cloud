(() => {
  "use strict";
  const targets = [...document.querySelectorAll('[data-report-blank-summary]')];
  if (!targets.length) return;
  for (const target of targets) {
    target.innerHTML = '<h2>空白格差異比較</h2><p class="report-blank-status" role="status">正在計算最近 48 期的空白格與對應球號…</p><div class="report-blank-panels"></div>';
  }
  const frame = document.createElement('iframe');
  frame.title = '空白格差異計算來源';
  frame.setAttribute('aria-hidden', 'true');
  frame.tabIndex = -1;
  frame.style.cssText = 'position:absolute;left:-10000px;top:0;width:1500px;height:1200px;border:0;visibility:hidden';
  let poll;
  const finish = (error) => {
    clearInterval(poll);
    clearTimeout(timeout);
    frame.remove();
    if (error) targets.forEach(target => {
      target.querySelector('.report-blank-status').textContent = '空白格摘要暫時無法載入，請重新整理或開啟空白格比較頁。';
    });
  };
  const timeout = setTimeout(() => finish(true), 90000);
  frame.addEventListener('load', () => {
    poll = setInterval(() => {
      try {
        const source = frame.contentDocument;
        const panels = [...source.querySelectorAll('#blank-difference-panels .overlay-panel')];
        if (panels.length !== 8 || panels.some(panel => !panel.querySelector('.blank-number-summary p'))) return;
        const cutoff = source.querySelector('#adjacent-date').textContent.replace(' 本期相鄰', '');
        for (const target of targets) {
          target.querySelector('.report-blank-status').textContent = `資料截至 ${cutoff}；依實際開獎期計算，每日隨資料更新。`;
          const container = target.querySelector('.report-blank-panels');
          for (const panel of panels) {
            if (!panel.querySelector('td.blank-changed .comparison-ball')) continue;
            const card = document.createElement('article');
            const heading = document.createElement('h3');
            heading.textContent = panel.querySelector('header strong').textContent;
            card.append(heading);
            const total = document.createElement('p');
            total.className = 'report-blank-total';
            total.textContent = panel.querySelector('.blank-summary').textContent;
            card.append(total);
            for (const item of panel.querySelectorAll('.blank-number-summary p')) {
              const line = document.createElement('p');
              line.textContent = item.textContent;
              card.append(line);
            }
            container.append(card);
          }
        }
        finish(false);
      } catch (_) { finish(true); }
    }, 200);
  }, {once:true});
  frame.src = 'handwritten-539-overlay.html?summary=1';
  document.body.append(frame);
})();
