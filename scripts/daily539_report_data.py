"""Calendar-based selection rules for the daily report."""
from datetime import date, timedelta
from collections import Counter


def omission_groups(draws, cutoff_date):
    """Latest draw has gap zero; count draws, rather than calendar days."""
    history = sorted((r for r in draws if r['draw_date'] <= cutoff_date),
                     key=lambda r: r['draw_date'], reverse=True)
    if not history or history[0]['draw_date'] != cutoff_date:
        raise ValueError('Omission history must reach the report cutoff')
    gaps = {}
    for gap, row in enumerate(history):
        for number in row['numbers']:
            gaps.setdefault(number, gap)
    if len(history) < 10:
        raise ValueError('At least ten draws are required for omission groups')
    return [{'gap': gap, 'numbers': sorted(n for n, value in gaps.items() if value == gap)}
            for gap in (3, 1, 8, 9)]


def whole_report_counts(data, groups, figure, summaries, brief, california, omissions=()):
    """Count displayed ball entries, excluding grid labels and this ranking itself."""
    counts = Counter({n: 0 for n in range(1, 40)})
    counts.update(ball['number'] for ball in data['lastWindowSnapshot'])
    for source in ('sim', 'real'):
        numbers = [n for group in data[source] for n in group['numbers']]
        counts.update(numbers)
        counts.update(set(numbers))
        counts.update(n for n, count in Counter(numbers).items() if count > 1)
    counts.update(n for n, _ in star_pairs(data['ranking']))
    for _ in range(2):
        counts.update(row['number'] for row in data['ranking'])
    counts.update(n for group in groups for n in group['numbers'])
    counts.update({n for group in groups for n in group['numbers']})
    counts.update(figure['sorted_numbers'])
    counts.update(figure['numbers'])
    counts.update(n for summary in summaries for group in summary['groups'] for n in group['numbers'])
    counts.update(n for group in brief['groups'] for n in group['numbers'])
    counts.update(n for group in omissions for n in group['numbers'])
    if california['draw']:
        counts.update(california['draw']['numbers'])
    return [{'number': n, 'count': count}
            for n, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def choose_target_date(report_date, cutoff_date, previous_target=None):
    """Keep the requested preview target until it is reached; never use a drawn target."""
    candidates = [date.fromisoformat(report_date),
                  date.fromisoformat(cutoff_date) + timedelta(days=1)]
    if previous_target:
        candidates.append(date.fromisoformat(previous_target))
    target = max(candidates)
    return target + timedelta(days=1) if target.weekday() == 6 else target


def remaining_groups(draws, target_date, cutoff_date):
    """Use corrected calendar offsets; move Sunday sources back to Saturday."""
    target = date.fromisoformat(target_date)
    cutoff = date.fromisoformat(cutoff_date)
    if cutoff >= target:
        raise ValueError('Report cutoff must precede the target date')
    available = [r for r in draws if date.fromisoformat(r['draw_date']) <= cutoff]
    by_date = {r['draw_date']: r for r in available}
    groups = []
    for offset in (5, 2, 11, 12):
        source = target - timedelta(days=offset)
        # User-selected source for the 2026-11-26 report's third group.
        if target_date == '2026-11-26' and offset == 11:
            source = date(2026, 11, 16)
        if source.weekday() == 6:
            source -= timedelta(days=1)
        source_date = source.isoformat()
        # Only fall back within published history; pending dates remain pending.
        if source <= cutoff and source_date not in by_date:
            earlier = [day for day in by_date if day < source_date]
            if earlier:
                source_date = max(earlier)
        row = by_date.get(source_date)
        later = {n for r in available if r['draw_date'] > source_date for n in r['numbers']}
        groups.append({'source_date': source_date, 'offset': offset,
                       'numbers': [n for n in row['numbers'] if n not in later] if row else [],
                       'available': row is not None})
    return groups


def star_pairs(ranking):
    columns = (4, 5, 7, 11, 17, 19, 24, 26, 28, 35)
    return sorted((ranking[col - 1]['number'], star) for star, col in enumerate(columns, 1))


def figure_nine(ranking):
    """Read score-anchored four-row columns from the left, ignoring decimals."""
    groups = []
    for row in ranking:
        score = int(row['score'])
        if not groups or groups[-1]['score'] != score:
            groups.append({'score': score, 'numbers': []})
        groups[-1]['numbers'].append(row['number'])
    if not groups:
        raise ValueError('Ranking is empty')
    first_height = min(4, len(groups[0]['numbers']))
    following_height = max(2, 5 - first_height)
    columns = []
    selected = []
    for group_index, group in enumerate(groups):
        for start in range(0, len(group['numbers']), 4):
            height = first_height if group_index == 0 and start == 0 else following_height
            numbers = group['numbers'][start:start + min(height, 9 - len(selected))]
            if numbers:
                columns.append({'score': group['score'], 'numbers': numbers})
                selected.extend(numbers)
            if len(selected) == 9:
                return {'columns': columns, 'shape': [len(c['numbers']) for c in columns],
                        'numbers': selected, 'sorted_numbers': sorted(selected)}
    raise ValueError('Ranking does not provide nine figure numbers')
