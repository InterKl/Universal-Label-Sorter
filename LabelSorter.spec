# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec — builds on macOS and Windows alike (PyInstaller
cannot cross-compile: run `pyinstaller LabelSorter.spec` separately on each
OS; the platform-specific bits below (BUNDLE .app, icon extension) branch on
sys.platform automatically).

Use --onedir (COLLECT), not --onefile: a ~300MB onefile bundle would
re-extract to a temp dir on every launch, adding 10-30s of startup each
time. Onedir starts immediately.

Three things a plain `pyinstaller run_app.py` invocation would silently get
wrong, learned from Streamlit's own packaging docs and confirmed by testing
this exact spec (the third by actually running the built app, not just
inspecting the build log):
  - collect_all('streamlit') is required for its compiled frontend assets
    (the static JS/CSS the browser loads) -- without them the app serves a
    blank page.
  - copy_metadata() is required for every package Streamlit inspects via
    importlib.metadata at runtime (it checks its own and its deps' versions
    on startup) -- without it the frozen app raises PackageNotFoundError
    before the server even starts, which `python run_app.py` from source
    never surfaces since the metadata is just sitting on disk normally.
  - collect_submodules('sorter') is required because PyInstaller's Analysis
    only statically follows imports reachable from the entry script
    (run_app.py). app.py -- the actual Streamlit script, which is what has
    `from sorter import auth, config, storage, ...` -- is bundled as inert
    *data* (Streamlit's bootstrap exec()s it at runtime) and is never
    scanned, so nothing it imports gets discovered on its own. Without this,
    the frozen app raises ImportError on every submodule app.py needs that
    run_app.py doesn't also happen to import.
"""
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

APP_NAME = "LabelSorter"
APP_VERSION = "1.0.0"  # keep in sync with sorter/version.py APP_VERSION

# collect_submodules('sorter') below walks the package by importing it, using
# whatever sys.path is active *right now* during spec-file execution -- it
# runs before Analysis() even exists, so Analysis(pathex=...) can't help it.
# Confirmed by testing: without this, it silently found only sorter.paths
# (imported directly by run_app.py) and missed the other 9 submodules that
# only app.py imports, even though the identical collect_submodules() call
# in a plain `python3 -c` from this same directory found all of them —
# CWD-on-sys.path isn't a given in the spec-exec context.
sys.path.insert(0, SPECPATH)

datas = [
    ("assets/fonts", "assets/fonts"),
    ("sku_map.json", "."),
    ("app.py", "."),  # run_app.py resolves this at runtime via resource_path()
]
binaries = []
hiddenimports = []

streamlit_datas, streamlit_binaries, streamlit_hiddenimports = collect_all("streamlit")
datas += streamlit_datas
binaries += streamlit_binaries
hiddenimports += streamlit_hiddenimports

# See module docstring: app.py's imports are invisible to static analysis,
# so force-include every sorter submodule regardless of whether run_app.py
# happens to import it too.
hiddenimports += collect_submodules("sorter")

# Streamlit resolves its own and several dependencies' versions via
# importlib.metadata at import time; PyInstaller strips package metadata by
# default, which turns that into a runtime crash rather than a warning.
for pkg in ("streamlit", "pandas", "numpy", "pyarrow", "altair", "pillow", "pydeck"):
    datas += copy_metadata(pkg)

a = Analysis(
    ["run_app.py"],
    # SPECPATH (this file's directory, injected by PyInstaller into the spec
    # exec context) must be on the search path explicitly: collect_submodules
    # silently found nothing beyond sorter/paths.py without it, even though
    # the same call in a plain `python3 -c` from this same directory returned
    # all 11 submodules -- CWD-on-sys.path isn't implied during spec
    # execution the way it is for an interactive interpreter.
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app - no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: add assets/icons/LabelSorter.icns (mac) / .ico (win) when available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=None,  # TODO: assets/icons/LabelSorter.icns
        bundle_identifier="com.labelsorter.app",
        info_plist={
            "NSHighResolutionCapable": "True",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHumanReadableCopyright": "",
            # Sorting is CPU-bound and takes real time (~17s per 100 pages);
            # this keeps macOS from suspending the app in the background.
            "LSBackgroundOnly": "False",
        },
    )
