"""Deadline state is computed on reads; historical ads are never deleted."""
from datetime import datetime, timezone, timedelta


def deadline_instant(value):
    if not value:return None
    try:
        if len(value)==10:
            deadline=datetime.strptime(value,'%Y-%m-%d')+timedelta(days=1)
        else:deadline=datetime.fromisoformat(value.replace('Z','+00:00'))
        if deadline.tzinfo is None:deadline=deadline.astimezone()
        return deadline.astimezone(timezone.utc)
    except (ValueError,TypeError):return None


def deadline_state(value,at=None):
    at=at or datetime.now(timezone.utc)
    deadline=deadline_instant(value)
    if deadline is None:return 'rok_nije_poznat'
    expired=deadline<=at
    return 'istekao' if expired else 'rok_nije_istekao'


def group_state(ads):
    known=[a for a in ads if deadline_state(a.get('expires',''))!='rok_nije_poznat']
    live=[a for a in known if deadline_state(a['expires'])=='rok_nije_istekao']
    # A missing deadline on a syndication does not extend an explicit deadline.
    status='rok_nije_istekao' if live else ('istekao' if known else 'rok_nije_poznat')
    dates=[a['expires'] for a in live or known]
    return status,max(dates,key=deadline_instant) if dates else ''
