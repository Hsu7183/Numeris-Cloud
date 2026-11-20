"""Calendar-based selection rules for the daily report."""
from datetime import date, timedelta


def choose_target_date(report_date, cutoff_date, previous_target=None):
    """Keep the requested preview target until it is reached; never use a drawn target."""
    candidates = [date.fromisoformat(report_date),
                  date.fromisoformat(cutoff_date) + timedelta(days=1)]
    if previous_target:
        candidates.append(date.fromisoformat(previous_target))
    return max(candidates)


def remaining_groups(draws, target_date, cutoff_date):
    """Use exact calendar dates; never substitute another draw for a missing day."""
    target = date.fromisoformat(target_date)
    cutoff = date.fromisoformat(cutoff_date)
    if cutoff >= target:
        raise ValueError('Report cutoff must precede the target date')
    available = [r for r in draws if date.fromisoformat(r['draw_date']) <= cutoff]
    by_date = {r['draw_date']: r for r in available}
    groups = []
    for offset in (4, 2, 10, 11):
        source_date = (target - timedelta(days=offset)).isoformat()
        row = by_date.get(source_date)
        later = {n for r in available if r['draw_date'] > source_date for n in r['numbers']}
        groups.append({'source_date': source_date, 'offset': offset,
                       'numbers': [n for n in row['numbers'] if n not in later] if row else [],
                       'available': row is not None})
    return groups


def star_pairs(ranking):
    columns = (4, 5, 7, 11, 17, 19, 24, 26, 28, 35)
    return sorted((ranking[col - 1]['number'], star) for star, col in enumerate(columns, 1))
