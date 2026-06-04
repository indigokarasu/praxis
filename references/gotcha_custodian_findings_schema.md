# Gotcha: Custodian Findings Schema

When Custodian reports findings to Praxis, the schema must match the expected format.

## Schema

```json
{
  "finding_id": "uuid",
  "type": "anomaly | corruption | drift | gap",
  "severity": "low | medium | high | critical",
  "source": "custodian",
  "timestamp": "ISO8601",
  "details": {}
}
```
