# Handover — Label Sorter Desktop App

Written at the end of a long build session, for whoever (human or AI) continues this project next.
Read this before touching anything — it'll save you from re-discovering things the hard way.

**Update (same day, commit `0b2193c`):** added a Lazada tab after this doc was first written. See
"Lazada tab" section below — it's a different shape from Shopee/TikTok (no label PDF at all).

**Update 2 (same day, commits `edbff77`→`f596373`, latest = `f596373`):** the Lazada สรุปรวม PDF
initially shipped with *only* the Total/กล่อง/ใบพัด tables, no order list — the owner caught this
immediately ("Why the order list in สรุปรวม") and it was added (`build_lazada_summary_pdf()`,
replacing the old `build_group_summary_pdf()`). Getting it to *visually match* Shopee/TikTok's PDF
took **two** follow-up commits, not one — see the new "process lesson" at the end of the Lazada
section below; it's a mistake worth not repeating.

Everything else in this doc is still accurate as of `f596373`.

## What this project is

A Streamlit app that lets non-technical warehouse staff process Shopee/TikTok/Lazada orders:
- **Shopee/TikTok:** upload packing list + label PDF → click Sort → download sorted PDF + order
  list + จำนวนใบพัด summary + สรุปรวม executive-summary PDF.
- **Lazada:** upload just the order xlsx (no label PDF exists for this platform) → rows get
  reversed top-to-bottom → download the reversed order list + a สรุปรวม PDF that has BOTH an
  order-numbered list (with the same green/yellow highlight rule as Shopee/TikTok) AND the
  Total/กล่อง/ใบพัด tables — same shape as the Shopee/TikTok summary PDF, adapted for a platform
  with no label pages to enumerate.

Ported from the owner's original ad-hoc scripts. Packaged as a native Mac/Windows desktop app
(PyInstaller) so staff never touch Python.

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

## 🔴 Open issue — Windows build won't start (still unresolved, paused not concluded)

The owner downloaded `LabelSorter-Windows-1.0.0.zip` from the CI build (see below), ran
`LabelSorter.exe`, and reported: **"just keep running no message appear nothing"** — no browser
opens, no visible error.

**Progress since this was first written:** the owner ran `python -m pip install -r requirements.txt`
then `python -m streamlit run app.py` directly from source on the Windows machine (had to use
`python -m pip`/`python -m streamlit` instead of bare `pip`/`streamlit` — those weren't on PATH) —
**and it worked.** The app loaded and ran correctly from source on Windows. This is an important
data point: **the app code itself has no Windows bug.** The problem is isolated to the packaging
layer (`run_app.py` and/or `LabelSorter.spec`), not `app.py`/`sorter/*`.

Owner was about to try building locally on the Windows machine when the conversation moved on to
the Lazada feature instead — **this thread is paused, not resolved.** Next step:

```cmd
cd Universal-Label-Sorter
python -m pip install -r requirements-dev.txt
python -m PyInstaller --clean --noconfirm LabelSorter.spec
dist\LabelSorter\LabelSorter.exe
```

Why it's hard to diagnose blind: `LabelSorter.spec` builds with `console=False` (no terminal
window — intentional, so non-technical staff never see a scary console), which means **any crash
or hang produces zero visible output on Windows.** If the local build *also* hangs silently, the
fastest way to actually see the error is to temporarily flip `console=False` → `console=True` in
`LabelSorter.spec`, rebuild, and read the traceback that appears in the now-visible console window.
**Don't ship a `console=True` build to staff** — flip it back once the bug is found.

Other things worth checking first (given to the owner, not yet confirmed either way):
1. A **Windows Firewall popup** hidden behind other windows (binding a listening socket can
   trigger this even on `localhost`) — click Allow if found.
2. **Task Manager** for `LabelSorter.exe`: present+alive but no browser → check if `MsMpEng.exe`
   (Windows Defender) is spiking CPU, a first-run scan of an ~86MB unsigned exe can take a
   minute-plus; not present at all → it crashed silently on startup.
3. Manually try **`http://localhost:8765`** in a browser — the server may have started fine while
   only `webbrowser.open()` in `run_app.py` failed silently (e.g., no default browser registered).

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
app.py                  Streamlit UI: Shopee / TikTok / Lazada / ตั้งค่า SKU / ประวัติ tabs
run_app.py               Desktop launcher — starts Streamlit in-process via bootstrap, opens browser
LabelSorter.spec         PyInstaller build spec (onedir). READ ITS DOCSTRING — documents 3
                         non-obvious bugs already found and fixed (see below)
sorter/
  paths.py               resource_path() (frozen-safe bundled-asset loading) + per-OS data dirs
                         (~/Library/Application Support/LabelSorter on Mac, %APPDATA%\LabelSorter
                         on Windows)
  config.py               SKU map resolution: shared Drive folder → local fallback → bundled seed.
                          Also load_lazada_group_config() — see "Lazada tab" below
  auth.py                 Admin/history passwords, same shared/local fallback pattern as config.py
  storage.py              Local batch history (save/list/purge), 30-day retention, per-machine.
                          save_batch() for Shopee/TikTok, save_lazada_batch() for Lazada (no label
                          PDF file written for those)
  version.py               App version + update-available check against the shared folder
  core.py                 Shared phase/group ranking, PDF reorder + integrity checks,
                          today_stamp() — see the Windows fix below
  shopee.py / tiktok.py    Platform-specific sort logic (ported from the original scripts)
  lazada.py                Lazada: SKU-strip translation, row reversal, กล่อง/ใบพัด summary —
                          see "Lazada tab" below, different shape from shopee.py/tiktok.py
  summary.py               จำนวนใบพัด summary transform (shared by Shopee/TikTok;
                          lazada.py has its own parallel version, see below for why)
  exec_summary.py          PDF generators (reportlab; bundled Thai font): build_exec_summary_pdf()
                          for Shopee/TikTok (fixed 60-row/3-column picking list + tables),
                          build_lazada_summary_pdf() for Lazada (order-numbered list, single column,
                          same highlight rule + same font/padding/column-width constants as the
                          Shopee/TikTok one — see "process lesson" in the Lazada section)
assets/fonts/             IBM Plex Sans Thai (SIL OFL) — bundled so Thai renders correctly
                          regardless of what fonts exist on a given staff machine
sku_map.json              Bundled seed (see the public-repo warning above) — copied out to the
                          active location on first run, never read again after that. Shopee/TikTok
                          only — Lazada doesn't use this file (see lazada_config.json below)
lazada_config.json        Lazada's group *display order* only — no SKU lookup table needed, the
                          translation is a deterministic rule (see below), not a dict
tests/                    Regression suite
.github/workflows/build.yml   CI: builds Mac .dmg + Windows .zip from a version tag (matrix build)
README.md                 Full staff install guide (Thai) + owner's release checklist
requirements.txt / requirements-dev.txt (adds pyinstaller)
```

## Lazada tab

Added after the initial desktop build (commit `0b2193c`), so it's a different shape from the rest
of this doc's original context. Key things to know if you touch this:

- **No label PDF for this platform at all.** Lazada orders are just an xlsx export with no
  corresponding shipping-label PDF workflow. The tab has one upload slot (order file only), and
  the "sort" is a **literal row reversal** (`df.iloc[::-1]`) — row 1 becomes row N, nothing more
  clever than that. Don't confuse this with the Phase A/B/C picking-order sort used for
  Shopee/TikTok; Lazada has no equivalent concept.
- **SKU translation is a rule, not a lookup table.** Lazada's `sellerSku` column already encodes
  the product label directly as `"<label>-<N>"` — e.g. `"16HO-3"` → `"16HO"`, `"18PP+จุก-1"` →
  `"18PP+จุก"`. The trailing `-N` is a price-tier/variant code, not part of the product identity.
  `sorter/lazada.py`'s `translate_lazada_sku()` just strips a trailing `-\d+` with regex — no
  `sku_map.json`-style dict to maintain. This was validated against **32 real examples the
  business owner typed out by hand**, with zero exceptions, including entries with no suffix at
  all (`"16M"`, `"ด้ามกระทะ"`) which pass through unchanged. If a future SKU code doesn't fit this
  pattern, that validation is exactly where to start debugging — check
  `translate_lazada_sku()` against the new code first before assuming something else broke.
- **No explicit quantity column.** Unlike TikTok's CSV (which has a `Quantity` field), Lazada's
  export has one row per unit. A repeat purchase of the same product within one order is assumed
  to show up as multiple rows sharing the same `orderNumber` — this was an explicit assumption
  confirmed with the owner (not observed directly; **the one real sample file only had
  single-item, single-quantity orders**, so this path is covered by `tests/test_lazada.py`'s
  synthetic fixture, not by real data). If a real multi-quantity Lazada order ever looks different
  than "repeated rows, same orderNumber," `load_line_items_lazada()` in `sorter/lazada.py` is
  where the assumption lives.
- **Why `sorter/lazada.py` doesn't reuse `sorter/summary.py`'s `summarize()`/`explode_y_to_lock()`
  directly:** those functions do SKU→label translation via a dict lookup
  (`config.sku_map`), which doesn't exist for Lazada (translation already happened by the time
  items reach the summary step). `split_fanblade_vs_box()` *is* reused directly — it only touches
  `order_size`/`qty` columns, no SKU dependency, so there was nothing to duplicate there.
- **`build_lazada_summary_pdf()`** (in `exec_summary.py`) is the Lazada summary PDF. It has BOTH an
  order-numbered list (`#`, Order Number, สินค้า, จำนวน) AND the Total/กล่อง/ใบพัด tables — this
  was *not* the first version shipped (see process lesson below). The list comes from
  `build_picking_rows_lazada()` in `sorter/lazada.py`, which:
  - walks the **reversed** dataframe (same row order as the xlsx download, so the PDF and the
    spreadsheet agree on sequence) and emits one entry per distinct `(order, label)` pair at its
    *first* occurrence — repeated rows of the same product in one order collapse into a single
    `qty=N` entry (mirrors Shopee/TikTok Phase B), while a mixed order keeps one row per distinct
    product (mirrors Phase C);
  - reuses the exact highlight semantics from `sorter.core.build_picking_rows` (green = whole row
    for single-product qty≥2; yellow = one cell per row for a mixed order — first item's `#` cell,
    every other item's `qty` cell), *not* a full-row yellow;
  - explodes `+จุก` items into a base-label row plus a `ตัวล็อคใบพัดลม` lock row, inheriting the
    parent's qty/highlight, same as the summary-table transform already did.

  **Process lesson — getting this to visually match Shopee/TikTok took two commits, not one:**
  commit `d6123e2` copied over the `ParagraphStyle` font/leading/padding constants and looked
  right in isolation, but the owner immediately noticed the จำนวน column was still a different
  width. Commit `f596373` found the actual cause: the `Table(..., colWidths=[...])` geometry had
  never been touched — Lazada's group tables were still using a hardcoded `30mm` qty column
  against Shopee/TikTok's `15mm` (literally double), missed because I updated the *style constants*
  I remembered changing and didn't re-diff the *whole* function against its Shopee/TikTok
  counterpart. **If you're asked to "make X match Y" on a copy-derived function, grep for every
  hardcoded number in both functions and diff them side by side — don't rely on remembering which
  constants you already touched.**

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
- **The Lazada tab, including the order-numbered picking list** — `translate_lazada_sku()`
  exact-matches all 32 owner-provided real examples with zero mismatches; the one real sample xlsx
  processes correctly (counts hand-verified); `picking_rows` sequence/highlight/lock-explosion
  logic covered by explicit asserts in `tests/test_lazada.py` (multi-qty repeat, mixed order,
  `+จุก` explosion — none present in the one real sample, so this is synthetic-fixture-only
  coverage, not real-data coverage); full browser round-trip (upload → process → both downloads →
  saved to history) with zero console errors, from source on Mac, confirmed again after both PDF
  follow-up commits. **Not** yet built into a frozen `.app`/`.exe`, and not tested against a real
  multi-quantity Lazada order (the row-repeat assumption is unconfirmed against real data — see the
  Lazada section above).
- **Lazada PDF visual match to Shopee/TikTok** — confirmed by eye (rendered PDF read back and
  compared) after both `d6123e2` (font/padding) and `f596373` (the actual column-width fix); regression
  suite re-run clean after each.

**❌ Not yet verified:**
- Whether the Windows launch fix (still paused — plain `streamlit run app.py` confirmed working
  from source on the owner's actual Windows machine; packaged `.exe` still doesn't start, narrowing
  the bug to `run_app.py`/`LabelSorter.spec`) also needs a rebuild that includes the Lazada changes.
  The Windows debugging thread and the Lazada feature happened in the same session but were never
  reconciled — **whatever build the owner tests next should include everything through `f596373`**,
  not just the pre-Lazada `v1.0.0` tag.
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
2. **Finish the Windows launch debugging.** Source confirmed working (see the open-issue section) —
   the owner was about to build locally with PyInstaller on the Windows machine itself when this
   got paused for the Lazada feature. Pick that back up: build locally, and if it still hangs
   silently, flip `console=True` in `LabelSorter.spec` temporarily to see the real traceback.
   **Make sure the code under test includes commits through `f596373`**, not just the original
   `v1.0.0` tag — the Lazada work landed after that tag and hasn't been through a Windows build yet.
3. Once Windows genuinely works end-to-end: set up the real shared Drive/Dropbox folder (structure
   documented in `README.md`), do the "bootstrap one machine" step (install, connect to shared
   folder, set admin password), then have **one real staff member** install cold, following the
   README, on a machine that's never had this app — that's the test that actually matters most.
4. Consider cutting a `v1.1.0` tag (or similar) once Windows is confirmed, so CI produces installers
   that actually include the Lazada tab — right now the only tagged release (`v1.0.0`) predates it.
   Bump `APP_VERSION` in both `sorter/version.py` and `LabelSorter.spec` together (currently `1.0.0`
   in both — keep them in sync, nothing enforces this automatically).
5. Consider app icons and code signing once the core flow is proven solid — not blocking, but the
   unsigned-app warnings are the biggest remaining piece of staff-facing friction.

## Running the regression suite

`tests/` (originally added in commit `cfefa05` — previously these only existed as ephemeral
scratchpad scripts and would have been lost when the session ended). All five pass as of `f596373`
(latest commit as of this writing):

```bash
cd "Label Sorter Desktop" && source .venv/bin/activate
python3 tests/adversarial.py            # 13 real-user-mistake scenarios, expect "0 BUG(s)"
python3 tests/build_synthetic_shopee.py # Phase A/B/C highlight rule, expect "PASS"
python3 tests/build_synthetic_tiktok.py # multi-page mixed-order dedup, expect "PASS"
python3 tests/test_layout.py            # 6/130/170-row PDF layout, expect 1/1/2 pages
python3 tests/test_lazada.py            # SKU-strip rule, row reversal, multi-qty/mixed/+จุก, expect "ALL LAZADA TESTS PASS"
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
