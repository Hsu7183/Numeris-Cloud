"""Calendar-based selection rules for the daily report."""
from datetime import date, timedelta


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
    for offset in (5, 3, 11, 12):
        source = target - timedelta(days=offset)
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
