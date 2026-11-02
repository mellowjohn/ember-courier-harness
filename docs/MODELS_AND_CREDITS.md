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

On November 2, 2026, a live Spark screenshot-input check through the installed
CLI correctly identified a test game's blue background and visible zero-token
count, without either answer in its prompt. Estimated usage was $0.026722 in
the shared promotional ledger, with no remaining reservation from that call.
This confirms image transport and basic visual reading; it does not establish
that every future aesthetic judgment is correct. New chat proposals use this
image-input path for [independent game verification](CHAT_BUILDS.md#inline-approval).

New conversations and reviewed runs use host-selected effort and time allowances.
Discussion uses medium reasoning with a five-minute request ceiling. Game code,
bug investigation and independent verification use high reasoning, usually with
a fifteen-minute ceiling. Editable source of at least 48 KiB or compound task
assignments receive thirty minutes; subsequent task repair attempts also receive
thirty minutes and retain the failed checks as feedback. Prepared asset/runtime
bundles do not inflate the editable-source size. These are ceilings, not minimum
durations or promises of completion. A fast successful request can finish early.
Chat with existing game source or an approved project plan conservatively uses
implementation effort because even a short follow-up can request code changes.

The installed CLI's `exec --help` confirms medium/high reasoning support. The
selected settings are frozen with each new chat request or reviewed run, bound
into saved provider captures and shown in progress. Quiet calls emit host
heartbeats, which establish only that the process is still running. Old pending
requests and runs without a saved execution policy retain their original settings.
Restart Ember to use the updated host for new work. Source-pinned existing runs
may require a newly reviewed run when host files have changed.

Every call still permits one model step and reserves the same $5. Larger tasks
use the host's existing sequence of implementation, browser checks, independent
verification and bounded repair attempts. A longer timeout does not grant model
tools, extra paid calls, project acceptance or bug closure. Approved time windows,
credit limits, stop controls and verification gates still constrain the work.

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
Muse Image shares this ledger with Spark. Its pinned `muse-image-1.0` model
reserves $0.01 for one requested image and settles by returned-image count, not
token usage. Existing Spark reservations and historical entries retain their
original $5 bounds. Image calls use the same owner-authorized Model API grant,
bound to the existing credential and shared ceiling; see
[the direct image workflow](ASSETS_2D.md#free-credits-and-preparation). A read-only
model-list check confirmed the existing Muse credential can access Muse Image
on November 1, 2026. A real one-image call subsequently succeeded and settled
$0.01 in the ledger. Johnathan confirmed the grant works with Spark and requested
image calls without repeated billing blockers. Meta's terms section 13.3 cover
the Model API Services rather than limiting credits to Spark. This verifies the
shared-service eligibility; it does not claim a newly observed account balance
or a billing receipt. The additional card-removal assertion and daily confirmation
gate are not required for this connection. No original holds or usage are reset.

An OS-held lock serializes reservations across sessions. Each Spark request reserves
$5 before dispatch. Muse Spark's shared input/output context limit is 1,048,576
tokens; at the higher Standard output rate of $4.25 per million tokens, one model
step costs at most $4.456448 at the verified rates. The $5 reservation conservatively
covers that bound. On November 1, Johnathan removed the metadata-only credit
inspection interruption. A failed call with no token counters, or unexpected
usage metadata, now retains its full reservation without freezing conversations
in other sessions. The previous metadata-only freeze is retired automatically
on the next reservation, preserving its reason in ledger history. Existing holds
and settled charges are never reset. The $150 ceiling still applies; reported
usage beyond the request's context or price bound stops further dispatches.

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

The displayed ceiling and available amount follow any lower limit saved in the
ledger, including a zero-credit rehearsal ceiling. Existing reservations remain
held when the ceiling is lowered; availability displays zero rather than a
negative amount. The original $150 ceiling cannot be raised through the ledger.

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
capture preserve the hold; changed evidence freezes the ledger again. This
historical repair is no longer needed for metadata-only freezes: uncertain usage
now retains its hold without an inspection interruption. Restart a running app
after updating so dispatches use the current accounting and no-retry setting.

Muse receives the actual response structure through native structured output,
with local references expanded and unsupported validation keywords omitted.
Optional fields travel as required nullable slots; dynamic maps such as
`asset_budget` travel as arrays of `{key,value}` entries. Ember restores omitted
optional fields and maps, rejects duplicate map keys, and validates the complete
original schema locally before a plan or build can proceed. This replaces the
JSON-encoded `payload` string, whose contents could contain malformed JSON even
when the outer envelope was valid. Native schema dispatch passed a live Muse
check on November 1, 2026. Invalid replies retain their capture and usage evidence
without being redispatched on replay. **Try a new reply** creates a new bounded
request after a terminal failure; interrupted turns retain **Retry reply** so a
saved successful response can be restored. Error messages distinguish settled
reported usage from a retained uncertain reservation. Shared schema fragments
include their definitions locally; missing, external or recursive references
stop before credit reservation or dispatch. Closed objects and explicit optional
slots accommodate the provider's structured-output format.
The incompatible planning schema caused the November 1 provider rejection; its
failed-call usage event had no model token counters, triggering the former freeze.
Failed captures now show the provider's error and ask for a new message, rather
than mislabeling that provider failure as a credit inspection or re-dispatching
the saved request automatically.

The sprite entity/state-machine schema exposed Meta's ten-level nesting ceiling
on November 2. Object-valued maps now use native rows with `key` beside the value's
fields, removing the extra `value` object; scalar maps retain `{key,value}` rows.
Values with their own `key` property retain the wrapper to avoid collisions.
The complete chat format now fits ten levels, including animation markers.
Optional fields that already allow null do not receive a second nullable wrapper.
The host checks response container depth before reserving credits or launching
Muse, restores maps and checks the full original schema after decoding, and still
rejects duplicate map keys. A real request using the complete chat format passed
on November 2 (estimated credits $0.033589). Historical failed captures and their
uncertain credit holds remain unchanged. See [Meta structured output limits](https://dev.meta.ai/docs/structured-output).

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
