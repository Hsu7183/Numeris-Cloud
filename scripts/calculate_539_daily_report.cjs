/* Reuse the published ranking and sliding-window algorithms verbatim. */
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const payload = JSON.parse(read('docs/data/daily539.json'));
const workbench = JSON.parse(read('docs/data/539-workbench.json'));
const source = read('docs/daily539_output.js');
const start = source.indexOf('  const latestNumbers');
const end = source.indexOf('  const scoreStrip');
if (start < 0 || end < start) throw Error('Ranking algorithm markers changed');
const calculate = new Function('payload', source.slice(start, end) + '\nreturn scores;');
const page = read('docs/workbench/539-sliding-window.html');
const a = page.indexOf('function mulberry32('), b = page.indexOf('function countHits(');
if (a < 0 || b < a) throw Error('Sliding-window algorithm markers changed');
const engine = new Function('rows', 'var PRIZE={5:8000000,4:20000,3:300,2:50,1:0,0:0};\n' +
  page.slice(a, b) + '\nREAL_ROWS=rows;return {simDataset,realDataset,windowStats,pickNums};');
const draws = workbench.draws;
if (payload.draws.length < 200 || draws.length < 200) throw Error('Insufficient source history');
for (const [i, row] of draws.entries()) {
  if (!/^\d{9}$/.test(row.draw_no) || !/^\d{4}-\d{2}-\d{2}$/.test(row.draw_date) ||
      row.numbers.length !== 5 || new Set(row.numbers).size !== 5 ||
      row.numbers.some(n => !Number.isInteger(n) || n < 1 || n > 39) ||
      (i && row.draw_date >= draws[i - 1].draw_date)) throw Error('Invalid workbench source');
}
for (let i = 0; i < 200; i++) {
  if (draws[i].draw_no !== payload.draws[i].draw_no ||
      JSON.stringify(draws[i].numbers) !== JSON.stringify(payload.draws[i].numbers)) {
    throw Error('Workbench and official statistics disagree');
  }
}
const e = engine(draws.slice().reverse().map(r => [r.draw_no, r.draw_date, r.numbers.join(' ')]));
const W = 18, seed = 20261025, simN = 600;
const real = e.realDataset(), simulated = e.simDataset(simN, seed);
const groups = data => ['hot', 'cold', 'overdue', 'hybrid'].map(strategy => ({
  strategy, numbers: e.pickNums(strategy, e.windowStats(data, data.length, W)),
}));
const ranking = calculate(payload);
const snapshotStats = e.windowStats(real, real.length, W);
const lastWindowSnapshot = Array.from({length:39}, (_,i) => i+1)
  .sort((a,b) => snapshotStats.gap[b]-snapshotStats.gap[a] || snapshotStats.freq[b]-snapshotStats.freq[a] || a-b)
  .map(number => ({number, frequency:snapshotStats.freq[number], gap:snapshotStats.gap[number]}));
if (ranking.length !== 39 || new Set(ranking.map(r => r.number)).size !== 39) throw Error('Invalid ranking');
process.stdout.write(JSON.stringify({cutoff: draws[0], W, seed, simN, realCount: real.length,
  windowStart: real[real.length - W], lastWindowSnapshot, ranking, sim: groups(simulated), real: groups(real), draws}));
