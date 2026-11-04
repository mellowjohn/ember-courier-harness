# Install and start Ember

The full app currently targets **Windows**. You need Python 3.12 or newer, an
internet connection for the first installation, a browser, and a writable folder.
Python 3.12 is the version used for the repository's installation checks. Git is
needed for the contract sample's commit/verification steps and contributor work;
it is not required to download a ZIP or open the app.

## Quick start on Windows

1. Install [Python](https://www.python.org/downloads/). If you use the Python install
   manager, run `py install 3.12` once. With the traditional installer, enable the
   Python launcher or **Add Python to PATH**.
2. [Download the repository ZIP](https://github.com/mellowjohn/ember-courier-harness/archive/refs/heads/main.zip)
   and **Extract all** to a folder you can keep, such as `Documents\Ember`.
   Open the extracted folder containing `Start Ember.cmd` and `pyproject.toml`.
   Keep the whole folder together; running inside the ZIP will not work.
3. Double-click **Start Ember.cmd**. On the first run it sets up Ember's private
   `.venv` and installs the Python dependencies. Leave the window open until
   setup finishes and your browser opens. If the browser does not open, copy
   the complete private link printed after `Ember app:` into your browser.
4. Choose **New session**, give it a name and choose where to keep your projects.

Later launches reuse the installation. Keep the launcher window open while using
Ember. To stop it, press **Ctrl+C** in that window; saved sessions remain on disk.
Each restart prints a new private link, so reopen Ember from that launch.

Setup needs no administrator access, virtual-environment activation, PowerShell
policy changes or global Python package installation. To install without opening
the app, double-click **Setup Ember.cmd**. Setup can be rerun after a failed
download or to repair dependencies. It does not sign in, make AI requests or
change the credit allowance.

## Enable AI chat

Ember uses **Muse Code** for AI chat. Follow Meta's official
[Muse Code installation guide](https://dev.meta.ai/docs/muse-code) and
[sign-in guide](https://dev.meta.ai/docs/muse-code/auth). Sign in with the Meta
account that holds your Muse Code subscription, then open **Muse settings →
Check subscription** in Ember. **My Muse Code subscription** is the default
connection. If the wrong account is active, switch accounts in Muse Code and
run the check again. The check uses no model turn.
The current integration detects its Windows version marker
at `%LOCALAPPDATA%\Programs\muse\.muse-version` and the matching
`muse-bin-<version>.exe` beside it. Other installation layouts are not currently
auto-detected. Setup reports whether that executable is present; this does not
verify your sign-in or billing access.

If you have your own promotional balance, set up the credential in Muse Code
or provide `META_API_KEY` in the environment that launches Ember. Then select
**My Model API promotional credits** and confirm your billing settings. Returning
promotional-credit users choose this option once after upgrading. Ember preserves
the existing ledger. See [models and credits](MODELS_AND_CREDITS.md). You can
manage local sessions and inspect saved work before connecting either account.

For a first game, save a **Project brief** with your goal, controls and visual
direction. Describe the game in chat, choose **Try proposed changes**, then
**Approve & play** when you are satisfied. See [the app guide](LOCAL_UI.md).

## Optional browser checks

Ordinary app startup and manual previews do not need Node.js. Automated gameplay
checks, task verification and overnight polish need Node.js, Playwright and
Chromium. Install [Node.js LTS](https://nodejs.org/en/download), reopen your terminal
so it can find Node, and run this from the Ember folder:

```powershell
& ".\Setup Ember.cmd" --browser
```

This also repairs the Python installation. Playwright is installed in
`.harness/browser-tools`; Chromium uses Playwright's local browser cache. The
download may take several minutes. Repeat the same command if it is interrupted.
No AI call is made. Advanced existing-tool overrides are `EMBER_NODE`,
`EMBER_PLAYWRIGHT_MODULE` and `EMBER_BROWSER_EXECUTABLE`.

Blender is needed only for editable 3D prop production. See
[the asset pipeline guide](ASSET_PIPELINE.md) for that separate setup.

## Check or update an installation

From PowerShell in the extracted Ember folder:

```powershell
& ".\Setup Ember.cmd" --check
```

This checks Python, installed dependencies, app imports, UI resources, and the
presence of Muse and browser tooling. Missing optional tools are reported without
failing the basic installation. It makes no AI request and does not install packages.

To update a Git checkout, stop Ember, run `git pull`, then run **Setup Ember.cmd**
and restart. With a downloaded ZIP, back up your data, extract the new version
to a separate folder, then copy its program files over your existing Ember folder.
Keep `.harness`, `.venv` and your project folders in place. Run setup and restart.
Updating in place preserves the absolute paths used by saved contracts.

If you relocate Ember, keep the old folder and backups until you have checked
your saved sessions and project locations. Run setup to create a fresh `.venv`;
virtual environments should not be copied between locations. Existing contracts
or source-pinned runs can require a new review after paths or program files change.

Keep **`.harness`** and your selected project folders backed up together. They
contain session history, approvals, evidence, the credit ledger and your games.
Preserve the existing ledger when updating or moving Ember; a fresh installation
does not reset actual credit usage. See [local project locations](LOCAL_UI.md).

## Troubleshooting

| Problem | What to do |
|---|---|
| Python was not found | Install Python 3.12+ using the link above, then reopen setup. With the install manager, run `py install 3.12`. |
| Setup cannot download packages | Check your connection or organization's proxy settings and rerun **Setup Ember.cmd**. The original package error stays visible in the window. |
| Access denied | Extract the complete repository to a writable folder under Documents and run setup there. |
| `.venv` is incomplete, moved, or uses an older Python | Stop Ember, rename `.venv` to `.venv-old`, and rerun setup. Keep `.harness` and project folders in place. |
| Missing module or app import failure | Run **Setup Ember.cmd**, then `--check`. If it still fails, retain the displayed error for troubleshooting. |
| Blank page or access denied after a restart | Use the complete new private link from the current launcher window. |
| Muse is not detected | Install and sign in to Muse Code; check its supported Windows location above, then restart Ember. |
| Muse sign-in or credit error | Open **Muse settings** and check your selected connection. See the [credit guide](MODELS_AND_CREDITS.md) for billing and usage limits. |
| Automated checks need Chromium | Install Node.js LTS, reopen the terminal and run **Setup Ember.cmd --browser**. |
| Address already in use with a custom port | Launch without `--port` to let Ember choose an available port. |

For scripted/headless Windows launches, set `EMBER_NO_BROWSER=1` to keep the
browser closed and `EMBER_NO_PAUSE=1` to prevent the stopped launcher from waiting
for a key. Arguments such as `--port 8765` and `--root PATH` pass through to the
app; `--root` selects where session data is kept.

## Manual and contributor setup

The setup helper is a standard-library Python script. On Windows:

```powershell
py -3.12 tools/setup_ember.py
.\.venv\Scripts\python.exe -m ember_harness.local_ui --open-browser
```

It installs the checkout in editable mode so source updates are picked up after
restarting; rerun setup when dependencies change. Keep the checkout, including
`examples/`, since the app reuses the sample workflow. For an offline Python
installation, supply a prepared directory of dependency and build wheels:

```powershell
py -3.12 tools/setup_ember.py --wheelhouse .harness/clean-install-wheelhouse
```

See [clean installation checks](PRODUCT_DEMO.md#clean-installation-check) for
preparing that directory. `--browser` downloads tooling separately and cannot be
combined with `--wheelhouse`.

On macOS/Linux, the Python library and basic local server can be installed with:

```sh
python3 tools/setup_ember.py
.venv/bin/python -m ember_harness.local_ui
```

Use Python 3.12+. The full Muse and automatic browser-tool discovery currently
target Windows; these commands do not establish full cross-platform support.

Run the offline checks with `.venv`'s Python:

```powershell
.\.venv\Scripts\python.exe tools/release_check.py
```

See [release verification](../README.md#verify-the-project) for the installed-wheel
and optional real-browser rehearsals.
