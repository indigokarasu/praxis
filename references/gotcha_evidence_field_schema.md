# Gotcha: Evidence Field Schema Variance in Events

## Problem

When scanning events.jsonl for dedup checks or pattern grouping, the evidence field may be:
- A dict with {source_journal, fingerprint, text} keys (standard form)
- A list of dicts (some legacy events)
- Missing entirely on very old events

Code that does evt.get('evidence', {}).get('fingerprint', '') crashes with
AttributeError on list-form evidence.

## Fix

Always use a type-guarded helper:

    def get_evidence_fingerprint(evt):
        ev = evt.get('evidence', {})
        if isinstance(ev, dict):
            return ev.get('fingerprint', '')
        elif isinstance(ev, list) and ev and isinstance(ev[0], dict):
            return ev[0].get('fingerprint', '')
        return ''

## Also: id vs event_id in Legacy Events

Legacy events may use 'id' instead of 'event_id':

    eid = evt.get('event_id', evt.get('id', ''))

## Production Script Safety

The production praxis_ingest_run.py is safe because it constructs its own events
with dict-form evidence. The bug only manifests in ad-hoc scripts that read back
from events.jsonl which contains records from multiple ingest cycles.
