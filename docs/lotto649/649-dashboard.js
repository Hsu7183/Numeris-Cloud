(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const pad = n => String(n).padStart(2, '0');
  let records = [], filtered = [], current = 0;
  const size = 50;
  function filter() {
    filtered = records.filter(d => (!el('from').value || d.draw_date >= el('from').value) &&
      (!el('to').value || d.draw_date <= el('to').value) &&
      (!el('number').value || d.numbers.includes(Number(el('number').value))) &&
      (!el('state').value || d.video_status === el('state').value));
    current = 0;
    render();
  }
  function render() {
    const pages = Math.max(1, Math.ceil(filtered.length / size));
    el('result').textContent = `共 ${filtered.length.toLocaleString()} 期`;
    el('rows').innerHTML = filtered.slice(current * size, (current + 1) * size).map(d =>
      `<tr><td>${d.draw_date}</td><td>${d.draw_no}</td><td>${d.numbers.map(pad).join('、')}</td><td>${(d.special_numbers || []).map(pad).join('、') || '未載入'}</td><td>${d.ball_set ?? '待核對'}</td><td>${d.direction ?? '待核對'}</td><td>${d.loading_start_number ?? '待核對'}</td><td>${d.video_status}</td></tr>`).join('');
    el('page').textContent = `${current + 1}／${pages} 頁`;
    el('previous').disabled = current === 0;
    el('next').disabled = current + 1 >= pages;
  }
  function recent() {
    const index = Number(el('cutoff').value);
    const available = records.slice(index);
    el('recent-panels').innerHTML = [6, 12, 18, 24, 30, 36, 42, 48].map(period => {
      const draws = available.slice(0, period);
      if (draws.length < period) return `<section><h3>近${period}期</h3><p>此截止期之前僅有${draws.length}期資料，未滿${period}期。</p></section>`;
      const counts = Array(50).fill(0);
      draws.forEach(d => d.numbers.forEach(n => counts[n]++));
      const numbers = Array.from({length:49}, (_, i) => i + 1).sort((a,b) => counts[b] - counts[a] || a - b);
      return `<section class="recent-panel"><h3>近${period}期主號 · ${draws.at(-1).draw_date}～${draws[0].draw_date}</h3><div class="frequencies">${numbers.map(n => `<span><b>${pad(n)}</b>${counts[n]}次</span>`).join('')}</div></section>`;
    }).join('');
  }
  async function load() {
    try {
      const response = await fetch('649-full-audit.json', {cache:'no-store'});
      if (!response.ok) throw Error('完整歷史讀取失敗');
      records = (await response.json()).slice().reverse();
      el('cutoff').innerHTML = records.map((d,i) => `<option value="${i}">${d.draw_date} · ${d.draw_no}期</option>`).join('');
      ['from', 'to', 'number', 'state'].forEach(id => el(id).addEventListener('input', filter));
      el('cutoff').addEventListener('change', recent);
      el('reset').onclick = () => { ['from', 'to', 'number', 'state'].forEach(id => {el(id).value = '';}); filter(); };
      el('previous').onclick = () => { if (current > 0) { current--; render(); } };
      el('next').onclick = () => { if ((current + 1) * size < filtered.length) { current++; render(); } };
      el('export').onclick = () => {
        const rows = [['日期','期號','主號','特別號','球組','方向','裝球起始','影片狀態'],
          ...filtered.map(d => [d.draw_date,d.draw_no,d.numbers.map(pad).join(' '),(d.special_numbers || []).map(pad).join(' '),d.ball_set ?? '待核對',d.direction ?? '待核對',d.loading_start_number ?? '待核對',d.video_status])];
        const csv = '\uFEFF' + rows.map(row => row.map(v => `"${String(v).replaceAll('"','""')}"`).join(',')).join('\r\n');
        const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
        const link = document.createElement('a'); link.href = url; link.download = '大樂透篩選資料.csv'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      };
      filter(); recent();
    } catch (error) { el('result').textContent = error.message; }
  }
  load();
})();
