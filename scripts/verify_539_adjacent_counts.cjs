const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const report = JSON.parse(fs.readFileSync(path.join(root, 'docs/539-adjacent-counts-backtest.json'), 'utf8'));
const history = JSON.parse(fs.readFileSync(path.join(root, 'reports/539-adjacent-source.json'), 'utf8'));
const html = fs.readFileSync(path.join(root, 'docs/539-adjacent-reference.html'), 'utf8');
const start = html.indexOf('    const totals');
const end = html.indexOf("    document.getElementById('numbers').innerHTML", start);
if (start < 0 || end < 0) throw Error('Page calculation not found');
const calculate = new Function('payload', html.slice(start, end) + '\nreturn ordered.map(n => ({number:n,count:totals[n]}));');
report.details.forEach((trial, i) => {
  const actual = calculate({draws:history.slice(i,i+200).reverse()});
  if (JSON.stringify(actual) !== JSON.stringify(trial.ranking)) throw Error('Mismatch: '+trial.target_draw_no);
});
if (JSON.stringify(calculate({draws:history.slice(-200).reverse()})) !== JSON.stringify(report.latest_ranking)) throw Error('Latest mismatch');
console.log(`PASS: all ${report.trials} trial rankings and latest ranking match adjacency count page.`);
