# Muse and hackathon billing credits

Johnathan authorized **up to $150 total in Muse free hackathon credits** on
October 30, 2026. This supersedes the earlier blanket prohibition on credit use.
The ceiling is shared across all Ember sessions in the workspace and survives
restarts. No cash charges, paid fallback, top-ups or spending beyond that ceiling
are authorized. Ordinary cash `spend_usd` remains zero. Workflow contract and
action approvals still apply.

Ember's app is **Muse only**, following Johnathan's later instruction that local
models overload his computer. It never auto-starts Ollama, and older sessions
open with Muse selected. New sessions open as conversations and can propose [browser builds for inline
approval](CHAT_BUILDS.md). Muse Spark 1.3 is
called through the installed, authenticated Muse Code CLI with one model step,
no attached workspace, empty preset, disabled shell/write/web/reminder/input
tools, no foreign personal context, and contributor mode off. No local model is
used as a fallback. The separate local adapter remains a library/example feature,
not an app path.

Each launch also sets `--config provider_retry.max_retries=0`. A one-step cap
alone does not disable provider-level retries. This setting was checked with the
installed CLI's enterprise configuration validator and a no-cost echo run on
October 30, 2026; unknown or conflicting per-run settings cause Muse to refuse the
launch. Ember never changes the user's global Muse configuration.

## Credits are separate from subscriptions

`muse usage --json` reports subscription allowance. Its `no_allowance` result does
not establish whether billing credits are available. Meta documents pay-as-you-go
API credentials and subscriptions as separate billing paths. The existing stored
Muse sign-in successfully completed a one-step `meta` request on October 30,
returning “Muse is connected” and reporting one model call, despite a null
subscription allowance. Credentials stay in Muse's existing credential store;
Ember does not copy them into the repository or session captures.

## Shared ledger

`.harness/muse-credits.json` records reservations and estimated settled usage.
An OS-held lock serializes reservations across sessions. Each request reserves
$5 before dispatch. Muse Spark's shared input/output context limit is 1,048,576
tokens; at the higher Standard output rate of $4.25 per million tokens, one model
step costs at most $4.456448 at the verified rates. The $5 reservation conservatively
covers that bound. Only one model call on the pinned model is accepted; unexpected
calls, retries or usage bounds freeze the ledger for inspection.

Reported input and output tokens settle the reservation at Standard rates:
$1.25/M input and $4.25/M output, rounded upward to a micro-dollar. Cached input
is conservatively counted at the full input rate. Missing or uncertain usage
keeps its $5 reservation after crashes or timeouts. No automatic retry is sent.
A saved completed reply can be reopened without another model call. Corrupted
captures are rejected. New requests are denied when estimated usage plus held
reservations cannot fit under $150. The ledger tracks Ember usage, not other
applications or teams; the billing dashboard remains authoritative for the actual
promotional balance. Recheck model pricing before adopting changed pricing or
models.

## Historical retry inspection

One saved October 30 request reported two attempts: one failed attempt and one
completed Spark call. Its valid response was preserved before the strict usage
check froze the ledger. The successful call reported 19,641 input and 3,061 output
tokens, conservatively estimated at $0.037561. Failed-attempt usage was missing.

The inspected recovery keeps the full $5 reservation. Bounding the failed Spark
attempt at the entire 1,048,576-token context charged at the higher output rate
gives $4.456448; together the bound is $4.494009, within the original $5 hold.
No credit was released or balance reset. Ledger snapshots and a recovery report
are retained under `.harness/credit-inspections/`. The saved response was restored
without dispatching another model request, and its proposal still requires owner
approval before project writes.

`CreditLedger.retain_inspected_retry` is a narrow trusted-host repair for this
bounded shape, with one pinned-model configuration, one failed attempt, one
completed call, a verified capture hash, and no other unresolved reservations.
It cannot clear other freeze reasons, larger/unbounded usage, changed captures,
or multiple outstanding requests. Subsequent reads of that exact inspected
capture preserve the hold; changed evidence freezes the ledger again. Unknown
future retries continue to freeze until inspected. Restart a running app after
installing this fix so new dispatches use the no-retry setting.

The initial live connection check reported 19,062 input and 85 output tokens,
settled conservatively at **$0.024189 estimated credits**. This is an estimate
from reported token usage, not a billing receipt.

## Official references verified October 30, 2026

- [Authentication and billing](https://dev.meta.ai/docs/muse-code/auth)
- [Models and context limits](https://dev.meta.ai/docs/models)
- [Pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits)
- [Headless execution](https://dev.meta.ai/docs/muse-code/extending)

The older Muse *review* adapter still supports manual imports and no-cost echo
captures. Its live-provider gate has not been widened; funded conversation calls
use the separate ledger-backed chat transport.
