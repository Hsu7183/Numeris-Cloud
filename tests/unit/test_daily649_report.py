"""Validate the 49-ball report against independently counted official main numbers."""
import json
from pathlib import Path
import subprocess
import unittest
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]


class LottoDailyReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(subprocess.check_output(
            ['node', str(ROOT / 'scripts/calculate_649_daily_report.cjs')], cwd=ROOT))

    def test_snapshot_uses_18_six_number_draws_without_specials(self):
        data = self.data
        window = data['draws'][:18]
        frequencies = Counter(n for row in window for n in row['numbers'])
        self.assertEqual(sum(r['frequency'] for r in data['lastWindowSnapshot']), 108)
        self.assertEqual({r['number']: r['frequency'] for r in data['lastWindowSnapshot']},
                         {n: frequencies[n] for n in range(1, 50)})
        self.assertEqual(len(data['cutoff']['special_numbers']), 1)
        self.assertNotIn(data['cutoff']['special_numbers'][0], data['cutoff']['numbers'])

    def test_all_49_ranked_and_each_strategy_has_six_unique_balls(self):
        data = self.data
        self.assertEqual({r['number'] for r in data['ranking']}, set(range(1, 50)))
        for source in ('real', 'sim'):
            self.assertEqual(len(data[source]), 4)
            for group in data[source]:
                self.assertEqual(len(set(group['numbers'])), 6)
                self.assertTrue(all(1 <= n <= 49 for n in group['numbers']))


if __name__ == '__main__':
    unittest.main()
