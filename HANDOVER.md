# Handover — Label Sorter Desktop App

Written at the end of a long build session, for whoever (human or AI) continues this project next.
Read this before touching anything — it'll save you from re-discovering things the hard way.

## What this project is

A Streamlit app that lets non-technical warehouse staff sort Shopee/TikTok shipping labels by
product (upload packing list + label PDF → click Sort → download sorted PDF + order list +
จำนวนใบพัด summary + สรุปรวม executive-summary PDF). Ported from the owner's original ad-hoc
scripts. Currently being packaged as a native Mac/Windows desktop app (PyInstaller) so staff never
touch Python.

## ⚠️ The one thing to check first

**The GitHub repo is PUBLIC**, not private:
```
$ gh api repos/InterKl/Universal-Label-Sorter --jq '{private,visibility}'
{"private":false,"visibility":"public"}
```
`sku_map.json` in that repo contains the **owner's real business data** — 37 real SKU codes mapped
to real Thai product names. This was never explicitly decided either way; the owner gave me an
existing repo URL and I pushed to it without confirming visibility. **Ask the owner whether this is
intentional before doing anything else.** If not, either flip the repo to private
(Settings → General → Danger Zone → Change visibility) or scrub the real SKU data out of the
committed `sku_map.json` and replace it with placeholders.

## 🔴 Open issue — Windows build won't start (unresolved when session ended)

The owner downloaded `LabelSorter-Windows-1.0.0.zip` from the CI build (see below), ran
`LabelSorter.exe`, and reported: **"just keep running no message appear nothing"** — no browser
opens, no visible error. This is the last thing being debugged when the session ended.

Why it's hard to diagnose blind: `LabelSorter.spec` builds with `console=False` (no terminal
window — intentional, so non-technical staff never see a scary console), which means **any crash
or hang produces zero visible output on Windows.**

Troubleshooting steps given to the owner, not yet confirmed:
1. Check for a **Windows Firewall popup** hidden behind other windows (binding a listening socket
   can trigger this even on `localhost`) — click Allow if found.
2. Check **Task Manager** for `LabelSorter.exe`:
   - Present, alive → check if `MsMpEng.exe` (Windows Defender) is spiking CPU — first-run
     antivirus scan of an ~86MB unsigned exe can take a minute-plus. Just wait it out.
   - Not present → it crashed silently on startup.
3. Manually try **`http://localhost:8765`** in a browser — the server may have started fine while
   only the auto-open-browser step (`webbrowser.open()` in `run_app.py`) failed silently (e.g., no
   default browser registered).

**If none of that resolves it**, the next step is building a *debug* variant with `console=True` in
`LabelSorter.spec` (temporarily — don't ship this to staff) so the actual traceback becomes visible
on Windows. That's the fastest way to stop guessing.

## Where things live

```
/Users/inter/Desktop/Claude_VScode/
├── shopee_label_sorter.py, tiktok_label_sorter.py,       ORIGINAL scripts. Untouched.
│   shopee_algo_version2.py, tiktok_order_summary.py,     Owner's local ad-hoc use only.
│   shopee_packing_list.py                                 Hardcoded paths, not a shared tool.
│
├── Label Web App/                                         Hosted-web-app version. Built first,
│                                                            then the project pivoted to desktop
│                                                            distribution (see "Why desktop" below).
│                                                            NOT maintained since the pivot — still
│                                                            has the Windows-breaking %-d%b bug.
│                                                            Kept for reference only.
│
└── Label Sorter Desktop/                                  ★ THE ACTIVE PROJECT ★
    ├── .git/  (remote: https://github.com/InterKl/Universal-Label-Sorter, branch main)
    ├── .venv/  (local dev venv, not committed)
    ├── dist/, build/  (local PyInstaller output from testing, not committed, safe to delete/rebuild)
    └── ... see Project Structure below
```

**Always work in `Label Sorter Desktop/`.** It's a copy of `Label Web App/` with the desktop-specific
changes layered on — never edit `Label Web App/` expecting it to affect the real product.

## How we got here (context that explains *why*, not just *what*)

1. Owner wanted `shopee_label_sorter.py`/`tiktok_label_sorter.py` (local scripts, hardcoded paths)
   turned into something non-technical staff could use: upload → click → download.
2. Built `Label Web App/` — a Streamlit app, tested extensively (byte-identical parity with the
   original scripts, adversarial testing, a real production bug fixed: **stale results after
   swapping files could let staff download the wrong batch's labels** — see git history / the
   `_upload_signature` mechanism in `app.py` if you ever touch that logic).
3. Explored hosting it (Streamlit Cloud → ruled out, ephemeral storage; Render free tier → ruled
   out, no persistent disk + 0.1 CPU too slow for a ~17s CPU-bound sort; GCS for storage was
   designed in but never built). Decision reversed: **staff work from different locations**, ruling
   out a same-LAN setup, and the owner preferred no recurring hosting cost / no server to maintain
   over the *simpler* web deployment. This tradeoff was made explicit and the owner chose desktop
   knowingly (see the "should it be a webapp instead" exchange near the end of the session) —
   **don't relitigate this without reason**, but do know it was a real tradeoff, not an oversight:
   desktop trades staff-side friction (Gatekeeper/SmartScreen clicks, per-machine updates) for
   zero hosting cost and offline-capable core sorting.
4. Pivoted to packaging as a native desktop app. `Label Sorter Desktop/` was created as a **copy**
   (never edited `Label Web App/` in place) and built out from there.

## Project structure (`Label Sorter Desktop/`)

```
app.py                  Streamlit UI: Shopee / TikTok / ตั้งค่า SKU / ประวัติ (History) tabs
run_app.py               Desktop launcher — starts Streamlit in-process via bootstrap, opens browser
LabelSorter.spec         PyInstaller build spec (onedir). READ ITS DOCSTRING — documents 3
                         non-obvious bugs already found and fixed (see below)
sorter/
  paths.py               resource_path() (frozen-safe bundled-asset loading) + per-OS data dirs
                         (~/Library/Application Support/LabelSorter on Mac, %APPDATA%\LabelSorter
                         on Windows)
  config.py               SKU map resolution: shared Drive folder → local fallback → bundled seed
  auth.py                 Admin/history passwords, same shared/local fallback pattern as config.py
  storage.py              Local batch history (save/list/purge), 30-day retention, per-machine
  version.py               App version + update-available check against the shared folder
  core.py                 Shared phase/group ranking, PDF reorder + integrity checks,
                          today_stamp() — see the Windows fix below
  shopee.py / tiktok.py    Platform-specific sort logic (ported from the original scripts)
  summary.py               จำนวนใบพัด summary transform
  exec_summary.py          สรุปรวม PDF generator (reportlab; bundled Thai font)
assets/fonts/             IBM Plex Sans Thai (SIL OFL) — bundled so Thai renders correctly
                          regardless of what fonts exist on a given staff machine
sku_map.json              Bundled seed (see the public-repo warning above) — copied out to the
                          active location on first run, never read again after that
tests/                    Regression suite (just added — see below)
.github/workflows/build.yml   CI: builds Mac .dmg + Windows .zip from a version tag (matrix build)
README.md                 Full staff install guide (Thai) + owner's release checklist
requirements.txt / requirements-dev.txt (adds pyinstaller)
```

## Three non-obvious bugs already found and fixed — don't reintroduce them

If you ever touch `LabelSorter.spec` or `run_app.py`, re-read these. They were each invisible until
the *actual frozen build* was run, not just inspected:

1. **`today_stamp()` in `sorter/core.py`** used to call `strftime("%-d%b")`. `%-d` is a POSIX/glibc
   extension — raises `ValueError` on Windows. Every single sort would have crashed there. Fixed
   with a portable f-string: `f"{now.day}{now.strftime('%b')}"`.

2. **`run_app.py` must call `bootstrap.load_config_options(flag_options)` before
   `bootstrap.run(...)`.** The `streamlit run` CLI does this automatically; calling
   `streamlit.web.bootstrap.run()` directly (as we do, to embed Streamlit in a frozen app) does
   *not* — it only registers a watcher for *future* config-file changes. Without this call, every
   flag (port, headless, etc.) is silently ignored and Streamlit falls back to all its defaults
   (port 8501 instead of our chosen port, with no error).

3. **`LabelSorter.spec` needs both `collect_submodules("sorter")` AND an explicit
   `sys.path.insert(0, SPECPATH)` called *before* that.** PyInstaller's static analysis only
   follows imports reachable from `run_app.py`. `app.py` — which has the actual
   `from sorter import auth, config, storage, ...` — is bundled as inert *data* (Streamlit's
   bootstrap `exec()`s it at runtime), so none of its imports are auto-discovered. Confirmed by
   directly inspecting the built executable's embedded PYZ archive: without the `sys.path` fix,
   `collect_submodules` silently returned only `sorter.paths` (the one module `run_app.py` itself
   imports) instead of all 11 submodules — even though the identical call in a plain
   `python3 -c "..."` from the same directory found all 11. The build *log* gave zero indication
   anything was wrong; only actually launching the frozen app and reading its runtime traceback
   revealed it (`ImportError: cannot import name 'auth' from 'sorter'`).

There's a fourth, smaller one: `sorter/auth.py`'s `set_admin_password()` originally *required* a
shared folder to be connected before any password could be set at all — but the UI text called
that step merely "recommended." Fixed by mirroring `config.py`'s local-fallback pattern. If you
ever see auth-related code requiring the shared folder unconditionally, that's this bug again.

## What's verified vs. not

**✅ Verified (actually run, not just read):**
- Core sort logic — byte-identical parity against the original scripts, before this session drifted
  the real Downloads-folder fixtures out of sync (see the "live files kept changing mid-session"
  saga in the transcript if curious — not a code issue, just testing hygiene worth knowing about).
- `Label Web App/` (hosted version) — full browser-driven testing via Playwright, all features.
- `Label Sorter Desktop/` running from source on Mac, via both `streamlit run app.py` and
  `python run_app.py`.
- **The actual frozen `.app` bundle on Mac** — built, launched, and driven end-to-end: sort →
  history auto-save → download → admin password bootstrap → SKU editor → History tab login →
  re-download from history. Thai text confirmed rendering correctly in the produced PDF.
- GitHub Actions CI — both `macos-latest` and `windows-latest` jobs completed successfully from
  tag `v1.0.0` (run https://github.com/InterKl/Universal-Label-Sorter/actions/runs/29763733789,
  ~2.5 min each). This proves the code *builds* cleanly on Windows; it does **not** prove the
  resulting `.exe` *runs* correctly — that's the open issue above.

**❌ Not yet verified:**
- The Windows `.exe` actually launching and working end-to-end (the open issue above).
- The shared Drive/Dropbox folder setup — never actually created. No staff have been onboarded.
- Multiple staff machines pointed at the same shared folder simultaneously (SKU sync, password
  bootstrap propagation) — tested with isolated fake-HOME directories standing in for "two
  machines" on one Mac, not two genuinely separate real machines.
- App icons — `LabelSorter.spec` has `icon=None` placeholders for both platforms; no `.icns`/`.ico`
  artwork exists yet.
- Code signing / notarization — currently fully unsigned on both platforms (Gatekeeper/SmartScreen
  warnings are expected and documented in `README.md`'s staff guide). An Apple Developer account
  ($99/yr) would remove the Mac warning; Windows signing is pricier (e.g. Azure Trusted Signing).

## Next steps, in order

1. **Resolve the repo-visibility question** (see the ⚠️ at the top) before doing anything else that
   touches the remote.
2. **Debug the Windows launch issue.** Start with the three troubleshooting steps above. If those
   don't resolve it, temporarily set `console=True` in `LabelSorter.spec`, rebuild via a new tag
   (or have the owner build locally on their Windows machine — they have one), and read the actual
   traceback.
3. Once Windows genuinely works end-to-end: set up the real shared Drive/Dropbox folder (structure
   documented in `README.md`), do the "bootstrap one machine" step (install, connect to shared
   folder, set admin password), then have **one real staff member** install cold, following the
   README, on a machine that's never had this app — that's the test that actually matters most.
4. Bump `APP_VERSION` in both `sorter/version.py` and `LabelSorter.spec` together whenever cutting
   a release (currently `1.0.0` in both — keep them in sync, nothing enforces this automatically).
5. Consider app icons and code signing once the core flow is proven solid — not blocking, but the
   unsigned-app warnings are the biggest remaining piece of staff-facing friction.

## Running the regression suite

Just added (`tests/`, commit `cfefa05`) — previously these only existed as ephemeral scratchpad
scripts and would have been lost when the session ended. All four pass as of this commit:

```bash
cd "Label Sorter Desktop" && source .venv/bin/activate
python3 tests/adversarial.py            # 13 real-user-mistake scenarios, expect "0 BUG(s)"
python3 tests/build_synthetic_shopee.py # Phase A/B/C highlight rule, expect "PASS"
python3 tests/build_synthetic_tiktok.py # multi-page mixed-order dedup, expect "PASS"
python3 tests/test_layout.py            # 6/130/170-row PDF layout, expect 1/1/2 pages
```

Output PDFs land in `tests/_output/` (gitignored) — open them to eyeball if a test's assertions
pass but you want to sanity-check the actual rendering.

## Useful commands

```bash
# Local dev run
cd "Label Sorter Desktop" && source .venv/bin/activate && python run_app.py

# Local PyInstaller build (macOS; Windows needs a Windows machine or CI)
pip install -r requirements-dev.txt
pyinstaller --clean --noconfirm LabelSorter.spec
open dist/LabelSorter.app   # or run dist/LabelSorter.app/Contents/MacOS/LabelSorter directly for logs

# Trigger a CI build
git tag vX.Y.Z && git push origin vX.Y.Z
gh run watch --repo InterKl/Universal-Label-Sorter   # or check the Actions tab

# Inspect what actually got bundled into a built exe (how bug #3 above was found)
python3 -c "
from PyInstaller.archive.readers import CArchiveReader
car = CArchiveReader('dist/LabelSorter.app/Contents/MacOS/LabelSorter')
pyz = car.open_embedded_archive('PYZ.pyz')
print(sorted(n for n in pyz.toc.keys() if 'sorter' in n.lower()))
"
```

## GitHub / gh CLI auth note

`gh` is installed at `/usr/local/bin/gh` on this machine and already authenticated as `InterKl`
(confirmed working — used to push commits and tags, and to watch/inspect CI runs during this
session). If a future session can't push, check `gh auth status` before assuming credentials need
re-setup from scratch — they may already be there.
