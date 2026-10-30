# Local workflow app

On Windows, double-click `Start Ember.cmd` in the repository folder. Leave its
window open while using Ember and open the private link it prints. Each launch
chooses an available port and a fresh private link; use the new link after a
restart. Closing the launcher stops the server, while saved sessions remain on
disk. This launcher runs directly on your desktop rather than in a temporary
agent command session.

From the repository folder, run:

```powershell
py -3.12 -m ember_harness.local_ui
```

Open the private loopback link printed by the launcher in a browser or the Codex
browser panel. Keep the launcher running. After installation, `ember-ui --root
"D:\Ember Harness\ember-courier-harness"` provides the same launcher. The source
checkout is required because the app reuses the existing product example.

Choose **New session** and enter a name. Ember uses **Muse only**; it does not
auto-detect or start Ollama or another local model. The main view is a chat: type
a prompt and send it to Muse Spark 1.3. New sessions start as conversations;
**Start sample workflow** explicitly starts the bounded product workflow. Review
packets appear inline in the chat. Model text cannot approve a contract or execute
an action. Activity and Results remain separate views beside Chat.

Muse Code must be installed and signed in. The Windows installation is detected
from its version marker. Each chat request runs one model step using the empty
preset, with shell, writes, web tools, reminders and user-input tools disabled.
No workspace or personal-context attachment is requested. Standard mode is
explicit; contributor mode is off for the call. Conversation context is supplied
from the saved session. Chat can propose concrete browser builds with up to eight HTML/CSS/JavaScript files, with an exact diff and
inline approval before any file write. See [Build from chat](CHAT_BUILDS.md) for
the supported target, preview, revisions and recovery.

Muse uses the authorized hackathon billing credits, tracked against a shared
$150 Ember ceiling. A missing Muse subscription allowance does not block this
pay-as-you-go path. See [models and credits](MODELS_AND_CREDITS.md).

Each prompt is saved before inference. Completed replies and the provider choice
survive app restarts and reboots. A pending reply is never automatically resent;
use **Retry reply** explicitly after an interrupted request. Repeated completed
message IDs return the saved reply without another model call.

The chat shows an activity panel immediately after sending. Saved checkpoints
show context preparation, Muse startup, observed provider start, response
streaming, reply validation and proposal preparation. The panel shows elapsed
time and received response character counts. During a quiet period it explicitly
says it is waiting for Muse's next update; it does not invent completion
percentages. **Request activity** expands the timestamped history, which is also
available under **Activity & audit**.

Progress survives a refresh or reopening the same session. A pending request is
shown as running only while its OS-held chat lock is active; an abandoned request
is marked interrupted and offers an explicit retry. Active requests do not show a
retry button. Provider output is reduced to observed event types and counts for
this display; prompts and raw provider event text are not echoed into the activity
panel. Builds still wait for your exact approval before changing project files.

The app runs the bounded integrated Ember Courier sample described in
[PRODUCT_DEMO.md](PRODUCT_DEMO.md). It is not yet a general project editor or
arbitrary workflow designer. Default fixes and concept images are deterministic
fixtures; intake is a fixture and the verifier is deterministic. The local app keeps the sample fix deterministic in Muse-only mode. The separate
local-agent example adapter remains available for offline regression coverage;
the app does not launch it, including for older saved sessions.

Activity shows execution output and the latest 100 audit entries. Results shows
the completed report; **Verify current evidence** refreshes the manifest and
current file checks rather than relying on the saved PASS. Run logs remain in
`.harness/ui/sessions/`; projects, review receipts and evidence remain in the normal
`.harness/demos/` folders.

Sessions save their name, model choice, timestamps, conversation, worker status
and logs under `.harness/ui/sessions/`. Conversations save automatically. **Rename session** opens the name field;
**Save changes** updates the name and timestamp. The sidebar highlights the selected session and
shows its status. Selecting another session leaves its worker running.

Workflows started in this version keep a versioned JSON step journal, saved with
atomic replacement and a disk flush. Completed steps are restored, so recovery
skips prior asset ingests, attempts, approvals, tests and commits. Each pending
review reopens the same hash-bound packet. An OS-held worker lock is released by
process death and reboot; concurrent resume requests cannot launch two workers.
After a reboot or stopped worker, select the session and choose **Resume workflow**.
The journal validates its source version, workspace file hashes, audit prefix,
contract bytes and owner receipts before continuing. Chat history remains
accessible independently of workflow recovery.

Recovery is conservative at a partial side effect: a stop during an unfinished
write, ingest, test execution, commit or audit write requires inspection, rather
than repeating work whose outcome is uncertain. Modified inputs, damaged journals
or changed workflow code also stop recovery. Completed checkpoints can resume,
including immediately after a recorded commit. Expired or revoked authority is
not extended by recovery. Declined and completed workflows cannot be restarted
through Resume. Sessions created before this version retain their history but
have no execution checkpoint to recover after their worker dies.


The server binds only to `127.0.0.1` on an automatically selected port. The
private launch link supplies a session token, kept in browser session storage;
API requests require that token and enforce the loopback Host and same-origin
policy. Keep the link private. This is a local trusted human host, not multiuser
authentication. Review data is rendered as text. Images are limited to PNGs from
the current workflow's reviewed paths; no arbitrary file browser is exposed.

Audit writers wait up to two seconds to acquire their store lock when a live
worker is briefly busy. This applies to both owner decisions and worker writes;
operations execute only after acquiring the lock. Persistent locks remain in
place and fail closed. The host never deletes another writer's lock, replays an
action to force it through, or retries unrelated file errors.

Run `py -3.12 -m unittest discover -s tests -p test_local_ui.py -v` for the HTTP
boundary and seven-checkpoint integration test. Recovery checks are in
`tests/test_session_recovery.py`; conversation durability checks are in
`tests/test_session_chat.py`. All decisions in that test are
explicit synthetic test responses, not owner approvals.
