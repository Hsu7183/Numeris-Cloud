import unittest

from scripts.daily539_report_data import remaining_groups, star_pairs, choose_target_date, figure_nine


class DailyReportTests(unittest.TestCase):
    def test_figure_nine_confirmed_november_23(self):
        numbers = [14,30,28,17,2,19,23,6,7,12,20,29,32,3,5,8,9]
        scores = [3.2,3.1,3.0] + [2.0]*10 + [1.0]*4
        result = figure_nine([{'number': n, 'score': s} for n,s in zip(numbers,scores)])
        self.assertEqual(result['shape'], [3,2,2,2])
        self.assertEqual(result['numbers'], [14,30,28,17,2,6,7,29,32])
        self.assertEqual(result['sorted_numbers'], [2,6,7,14,17,28,29,30,32])

    def test_figure_nine_photo_shapes_and_score_resets(self):
        for counts, expected in [([1,4,3,1],[1,4,3,1]),
                                 ([2,5,8],[2,3,1,3]),
                                 ([4,2,2,1],[4,2,2,1])]:
            ranking=[]
            for i,count in enumerate(counts):
                for _ in range(count):
                    ranking.append({'number':len(ranking)+1,'score':4-i})
            result=figure_nine(ranking)
            self.assertEqual(result['shape'],expected)
            self.assertEqual(len(set(result['numbers'])),9)

    def test_preview_target_does_not_skip_on_midnight(self):
        self.assertEqual(str(choose_target_date('2026-11-21', '2026-11-20', '2026-11-21')), '2026-11-21')
        self.assertEqual(str(choose_target_date('2026-11-20', '2026-11-19', '2026-11-21')), '2026-11-21')
        self.assertEqual(str(choose_target_date('2026-11-21', '2026-11-21', '2026-11-21')), '2026-11-23')

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
        groups = remaining_groups(self.rows, '2026-11-21', '2026-11-19')
        self.assertEqual([g['numbers'] for g in groups],
                         [[11, 21], [20, 22, 27, 35, 39], [1, 19, 34], [7, 28, 33]])

    def test_calendar_shift_and_future_draw_excluded(self):
        rows = self.rows + [{'draw_date': '2026-11-20', 'numbers': [1, 2, 5, 14, 19]}]
        provisional = remaining_groups(rows, '2026-11-22', '2026-11-19')
        self.assertEqual([g['numbers'] for g in provisional],
                         [[5, 17, 26, 32, 38], [2, 10, 23, 24, 37], [14, 29], [1, 19, 34]])
        final = remaining_groups(rows, '2026-11-22', '2026-11-20')
        self.assertEqual([g['numbers'] for g in final],
                         [[17, 26, 32, 38], [10, 23, 24, 37], [29], [34]])

    def test_missing_source_is_not_substituted(self):
        groups = remaining_groups(self.rows, '2026-11-23', '2026-11-19')
        self.assertFalse(groups[1]['available'])
        self.assertEqual(groups[1]['source_date'], '2026-11-20')
        self.assertEqual(groups[1]['numbers'], [])

    def test_corrected_november_24_source_dates(self):
        groups = remaining_groups(self.rows + [{'draw_date': '2026-11-21', 'numbers': [19,20,28,30,32]}], '2026-11-24', '2026-11-23')
        self.assertEqual([g['source_date'] for g in groups],
                         ['2026-11-19', '2026-11-21', '2026-11-13', '2026-11-12'])

    def test_sunday_source_moves_to_saturday(self):
        groups = remaining_groups(self.rows + [{'draw_date': '2026-11-21', 'numbers': [19,20,28,30,32]}], '2026-11-25', '2026-11-24')
        self.assertEqual(groups[1]['source_date'], '2026-11-21')

    def test_requested_four_dates(self):
        groups = remaining_groups(self.rows + [{'draw_date': '2026-11-21', 'numbers': [19,20,28,30,32]}], '2026-11-24', '2026-11-23')
        self.assertEqual([g['source_date'] for g in groups],
                         ['2026-11-19', '2026-11-21', '2026-11-13', '2026-11-12'])

    def test_missing_historical_date_uses_previous_draw(self):
        rows = [r for r in self.rows if r['draw_date'] != '2026-11-19']
        groups = remaining_groups(rows, '2026-11-24', '2026-11-23')
        self.assertEqual(groups[0]['source_date'], '2026-11-18')
        self.assertTrue(groups[0]['available'])

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
