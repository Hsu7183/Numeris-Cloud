import unittest

from scripts.daily539_report_data import remaining_groups, star_pairs, choose_target_date


class DailyReportTests(unittest.TestCase):
    def test_preview_target_does_not_skip_on_midnight(self):
        self.assertEqual(str(choose_target_date('2026-11-21', '2026-11-20', '2026-11-21')), '2026-11-21')
        self.assertEqual(str(choose_target_date('2026-11-20', '2026-11-19', '2026-11-21')), '2026-11-21')
        self.assertEqual(str(choose_target_date('2026-11-21', '2026-11-21', '2026-11-21')), '2026-11-22')

    def setUp(self):
        self.rows = [
            {'draw_date': day, 'numbers': nums} for day, nums in [
                ('2026-11-09', [7, 9, 28, 30, 33]),
                ('2026-11-10', [1, 19, 24, 29, 34]),
                ('2026-11-11', [14, 21, 29, 30, 32]),
                ('2026-11-12', [2, 9, 30, 37, 38]),
                ('2026-11-13', [8, 11, 17, 38, 39]),
                ('2026-11-14', [3, 6, 20, 30, 32]),
                ('2026-11-16', [11, 21, 22, 35, 37]),
                ('2026-11-17', [5, 17, 26, 32, 38]),
                ('2026-11-18', [20, 22, 27, 35, 39]),
                ('2026-11-19', [2, 10, 23, 24, 37]),
            ]
        ]

    def test_user_example(self):
        groups = remaining_groups(self.rows, '2026-11-20', '2026-11-19')
        self.assertEqual([g['numbers'] for g in groups],
                         [[11, 21], [20, 22, 27, 35, 39], [1, 19, 34], [7, 28, 33]])

    def test_calendar_shift_and_future_draw_excluded(self):
        rows = self.rows + [{'draw_date': '2026-11-20', 'numbers': [1, 2, 5, 14, 19]}]
        provisional = remaining_groups(rows, '2026-11-21', '2026-11-19')
        self.assertEqual([g['numbers'] for g in provisional],
                         [[5, 17, 26, 32, 38], [2, 10, 23, 24, 37], [14, 29], [1, 19, 34]])
        final = remaining_groups(rows, '2026-11-21', '2026-11-20')
        self.assertEqual([g['numbers'] for g in final],
                         [[17, 26, 32, 38], [10, 23, 24, 37], [29], [34]])

    def test_missing_source_is_not_substituted(self):
        groups = remaining_groups(self.rows, '2026-11-22', '2026-11-19')
        self.assertFalse(groups[1]['available'])
        self.assertEqual(groups[1]['source_date'], '2026-11-20')
        self.assertEqual(groups[1]['numbers'], [])

    def test_target_result_must_not_be_used(self):
        with self.assertRaises(ValueError):
            remaining_groups(self.rows, '2026-11-19', '2026-11-19')

    def test_star_columns_are_mapped_before_sorting(self):
        ranking = [{'number': n} for n in range(39, 0, -1)]
        expected = sorted((40 - col, i) for i, col in
                          enumerate((4, 5, 7, 11, 17, 19, 24, 26, 28, 35), 1))
        self.assertEqual(star_pairs(ranking), expected)


if __name__ == '__main__':
    unittest.main()
