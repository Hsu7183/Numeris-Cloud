import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.california_daily import parse_draws, refresh


def row(numbers, draw_date='2026-11-24'):
    return '<tr><td>第&nbsp;12070&nbsp;期<p>' + draw_date + '</p></td><td>' + ''.join(
        f'<strong>{n}</strong>' for n in numbers) + '</td><td>99</td></tr>'


class CaliforniaDailyTests(unittest.TestCase):
    def test_extract_same_row_and_ignore_statistics(self):
        draw = parse_draws(row([13, 15, 17, 31, 34]))['2026-11-24']
        self.assertEqual(draw['draw_no'], '12070')
        self.assertEqual(draw['numbers'], [13, 15, 17, 31, 34])

    def test_reject_incomplete_duplicate_and_out_of_range(self):
        for balls in ([1, 2, 3, 4], [1, 2, 3, 4, 4], [1, 2, 3, 4, 40]):
            with self.subTest(balls=balls), self.assertRaises(ValueError):
                parse_draws(row(balls))

    def test_missing_today_does_not_relabel_yesterday(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('scripts.california_daily.urlopen') as fetch:
                fetch.return_value.__enter__.return_value.read.return_value = row([1, 2, 3, 4, 5], '2026-11-23').encode()
                result = refresh(Path(folder), '2026-11-24')
            self.assertEqual(result['status'], 'pending')
            self.assertIsNone(result['draw'])
            self.assertIn('2026-11-23', result['draws'])


if __name__ == '__main__':
    unittest.main()
