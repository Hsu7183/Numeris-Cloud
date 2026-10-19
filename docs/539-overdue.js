/* Draws must be ordered newest first. Latest draw has an omission of zero. */
((root) => {
  "use strict";
  const periods = [6, 12, 18, 24, 30, 36, 42, 48];
  const analyze = (draws) => {
    const factors = Array.from({ length: 39 }, (_, i) => ({ number: i + 1, count: 0 }));
    const windows = periods.map((period) => {
      const recent = draws.slice(0, period);
      if (recent.length < period) throw new Error(`不足 ${period} 期開獎資料`);
      const ranking = factors.map(({ number }) => {
        const index = recent.findIndex((draw) => draw.numbers.includes(number));
        return { number, omission: index < 0 ? period : index, atLeast: index < 0 };
      }).sort((a, b) => b.omission - a.omission || a.number - b.number);
      const top = ranking.slice(0, 5);
      top.forEach(({ number }) => { factors[number - 1].count += 1; });
      return { period, top };
    });
    factors.sort((a, b) => b.count - a.count || a.number - b.number);
    return { windows, factors };
  };
  root.daily539Overdue = { analyze };
})(globalThis);
