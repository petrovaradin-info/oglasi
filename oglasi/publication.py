"""Publication policy and atomic snapshots; does not mutate collected history."""
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from itertools import combinations
from pathlib import Path
from .dedup import match
from .lifecycle import group_state, deadline_instant

FRESH_DAYS = 14

def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None

def publication_state(ads, at=None):
    at = at or datetime.now(timezone.utc)
    state, deadline = group_state(ads)
    seen = [t for a in ads if (t := timestamp(a.get('last_seen'))) and t <= at]
    last = max(seen) if seen else None
    reasons = []
    if state == 'istekao': reasons.append('istekao_rok')
    if state == 'rok_nije_poznat' and (last is None or at >= last + timedelta(days=FRESH_DAYS)):
        reasons.append('nije_skoro_pronadjen')
    # Existing groups can predate stricter dedup rules. Quarantine, never split history here.
    if any(not match(a, b)[0] for a, b in combinations(ads, 2)):
        reasons.append('proveriti_spajanje')
    until = deadline_instant(deadline) if deadline else (last + timedelta(days=FRESH_DAYS) if last else None)
    return {'vidljiv': not reasons, 'razlozi': reasons,
            'poslednji_pronalazak': last.isoformat() if last else '',
            'vidljiv_do': until.isoformat() if until else ''}

def public_document(groups):
    from .platform_export import cards
    at = datetime.now(timezone.utc)
    visible, review = [], []
    for group in groups:
        policy = publication_state(group['sources'], at)
        row = cards([group])[0]
        row.update(policy)
        if policy['vidljiv'] and row['link'] and row['naslov'].strip():
            visible.append(row)
        elif row['status'] != 'istekao':
            review.append({'id': row['id'], 'naslov': row['naslov'], 'poslodavac': row['poslodavac'],
                           'izvori': row['izvori'], 'razlozi': policy['razlozi'] or ['nedostaje_naslov_ili_link']})
    return {'schema_version': '1.0', 'generated_at': at.isoformat(),
            'unknown_deadline_max_age_days': FRESH_DAYS, 'count': len(visible),
            'oglasi': visible}, review

def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name+'.', suffix='.tmp', delete=False) as handle:
            name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name): os.unlink(name)
