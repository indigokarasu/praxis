# Gotcha: OAuth Token Corruption from Disk-Full (ENOSPC)

## Problem
When disk fills to 100% (ENOSPC), cached OAuth token files can become **corrupted** — not just expired, but structurally invalid. This is a distinct failure mode from normal token expiry.

## How It Differs from Normal Expiry
| Normal Expiry | ENOSPC Corruption |
|---------------|-------------------|
| Token refresh succeeds silently | MCP auto-disables after 4 consecutive failures |
| `expired` state in finch scans | `REAUTH_NEEDED` state — user must re-consent |
| Re-auth not required | Full re-auth consent flow required |
| Token files intact | Token files may be 0 bytes or contain garbage |

## Detection
- Finch scan reports `google_oauth: REAUTH_NEEDED` (not just `EXPIRED`)
- Custodian scan flags `google_token_missing` after a prior disk-full event
- MCP google-workspace auto-disabled (check `blockers[]` for `google_oauth_reauth_required`)

## Signal Extraction
When a finch/custodian journal reports `REAUTH_NEEDED` AND there's a recent disk-full event (within 24h), record an escalation event with:
- `signal_type: "escalation"`
- `category: "oauth_corruption"`
- `failure_phase: "execution"`
- `domain: "system"`

Then check for existing active shifts about OAuth token verification — if one exists about token *existence*, the new shift should cover token *integrity* (they are complementary).

## Production Impact
- First occurrence: 2026-05-31 (disk-full at 100% corrupted tokens that were already expired 8+ days)
- All email/calendar/drive scanning blocked until manual re-auth
- Disk cleanup (freeing 42G) resolved disk-full but did NOT fix token corruption

## Related
- SKILL.md gotcha: "OAuth token corruption from disk-full" (pointer)
- `references/session_20260531_ingest9.md` — first detection and shift activation
