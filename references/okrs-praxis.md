# Praxis — OKR Definitions

## Skill-Specific OKRs

| OKR | Target | Window | Measurement |
|-----|--------|--------|-------------|
| `event_coverage` | ≥0.90 | 30 runs | Fraction of skill journals scanned vs total available |
| `lesson_extraction_precision` | ≥0.80 | 30 runs | Fraction of extracted lessons that produce valid shifts |
| `shift_activation_accuracy` | ≥0.75 | 20 activations | Fraction of activated shifts that improve target metric |
| `shift_decay_compliance` | ≥0.95 | 30 days | Fraction of stale shifts (14+ days no reinforcement) properly expired |
| `pattern_detection_noise` | ≤0.10 | 30 runs | Fraction of extracted lessons that are noise (unknown domain, signal_type unknown) |
| `cap_efficiency` | ≥0.80 | 30 days | Active shift slots used for distinct patterns (not near-duplicates) |

## Universal OKRs

From spec-ocas-journal.md: `schedule_adherence` (≥0.95), `data_integrity` (≥0.99).