# Automatic specialist delegation

**Run task with Muse** now selects specialists from the selected approved task.
The host prepares an ordered route and the exact child contracts together. The
task-run card shows the assignments before approval and the active agent during
execution. Preparing the route makes no model call. Approving the run starts
automatic handoffs within those reviewed permissions; final build, asset and
task acceptance retain their existing reviews.

| Work named in the task | Assignment |
| --- | --- |
| Rules, movement, controls, scoring, collision or progression | Gameplay specialist |
| UI, HUD, menus, responsive layout or accessibility | Interface specialist |
| Particles, trails, animation timing or scripted effects | VFX specialist |
| Multiple specialties | Two workers in sequence, then an independent verifier |
| Gameplay, interface and effects together | Gameplay specialist, then a presentation specialist covering interface and effects |
| Other browser work | One browser-game specialist, then the verifier |
| First browser game without an explicit artwork exclusion | Artwork specialist using Muse Image, game implementation specialist, then the verifier |
| Reviewed finding fix | One bug-fix specialist, frozen reproduction and separate verifier |
| Native chest/waygate production | Prop concept specialist, human direction pick, Blender production specialist and asset verifier |

Routing uses bounded word matches in the selected task title, with a general
worker as fallback. It is a host policy, not another model call or an unrestricted
planner. Explicit, unambiguous requests such as “Create original chest prop” or
“Model courier waygate” select the existing native production adapter. Requests
about existing assets, scene integration, inventory or interface code keep the
browser-task route. The explicit chest/gate controls remain available. The
production adapter still requires its supported project shape,
Blender and offline runtime; automatic routing cannot supply missing permissions.

There are at most two implementation workers, running sequentially. Each has a
distinct identity and a child contract within the approved project scope. Coding
workers write separate candidate directories and their own model-call contexts.
The second worker receives the first worker's materialized, validated source;
the final verifier receives the combined candidate without either worker's
narrative. Concept and production workers likewise have separate native output
areas. The concept worker cannot produce the final asset, and the producer cannot
rewrite concepts or choose a direction. Fixed packaging and browser drivers are
host operations under their existing gates.

The route is included in the exact review and bound to every child contract.
Source, feedback and model replies cannot create additional agents or stages.
Model calls reject a mismatched assignment. Contexts, results and candidate writes
use the existing hash-bound audit checkpoints. Resuming a run replays completed
stages, verifies their artifacts and continues the interrupted stage with the
same attempt allocation. A changed intermediate candidate also blocks promotion,
even when the final candidate is unchanged.

Coding runs with one worker keep up to three attempts and two model calls per
attempt. Two-worker runs allow up to two attempts and three calls per attempt,
so all scheduled calls fit the existing $30 bound at the full $5 reservation per
call. Both share the durable $150 promotional-credit ledger. The task's attempt
allowance persists across new runs; a run ending after two attempts does not
grant a fresh task allowance. Findings keep their one-attempt/$10 rules. Native
production keeps its existing directions/refinement budget and explicit pick.
See [task execution](TASK_RUNS.md), [asset production](ASSET_PRODUCTION.md) and
[credit controls](MODELS_AND_CREDITS.md).

New visual browser games prepare and bind their character and
environment artwork before the implementation handoff. An explicit artwork task
can also add the first prepared artwork to an existing game. Compatible library
assets are reused; missing sheets use the existing Muse Image adapter. The
review freezes the inventory, entity-plan context, image allowance and adapter
source. Completed images replay across interruption and coding repairs. The
implementation worker preserves the generated packages; the verifier receives
their metadata and checks the combined scene. Native chest/gate production keeps
its concept and Blender route. Explicit procedural-only/text-only or no-generated-art requests and games with
prepared artwork keep the ordinary coding route. Direct chat builds also receive artwork-first
planning instructions through their existing entity-plan path.

Artwork runs use one initial artwork call, at most eight image generations, and up to two coding/verifier attempts. Full text
reservations and all images fit the same $30 run ceiling and shared $150 ledger.
Missing image credit coverage stops generation without substituting shape art.
Every changed atlas still needs individual human acceptance in the exact build.

Accepting a task selects the first unfinished task in plan order and prepares its
run review. The next run starts after its separate contract approval. Missing
checks, credits, tooling or active work leave a visible continuation blocker;
acceptance of the previous task is retained. Once all task outcomes are accepted,
continuation stops. General engine production, arbitrary tools and character
modeling remain separate work.

`tests/test_orchestration.py` exercises routing, worker caps, actual sequential
handoffs, final verification/promotion, role boundaries, recovery and tampering
with synthetic model replies. Existing task, finding and asset-run suites cover
their shared gates. These checks use no live Muse credits.
