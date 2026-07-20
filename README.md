# จัดเรียงใบปะหน้า — Label Sorter Desktop App

แอปสำหรับพนักงาน (Mac/Windows) ที่ใช้จัดเรียงใบปะหน้า Shopee/TikTok โดยไม่ต้องติดตั้ง Python
เปิดแอปแล้วใช้งานผ่านเบราว์เซอร์ที่เปิดขึ้นมาอัตโนมัติ

## สำหรับพนักงาน (Staff install guide)

### ครั้งแรก — ติดตั้งแอป

**Mac:**
1. ดาวน์โหลด `LabelSorter-Mac-x.x.x.dmg` จากโฟลเดอร์ที่ใช้ร่วมกัน แล้วเปิดไฟล์
2. ลาก **LabelSorter** ไปใส่ในโฟลเดอร์ **Applications**
3. เปิดแอปครั้งแรก: macOS จะเตือนว่า "ไม่สามารถยืนยันผู้พัฒนาได้" (Gatekeeper) — นี่เป็นเรื่องปกติสำหรับแอปที่ยังไม่ได้จ่ายค่าลงทะเบียนนักพัฒนา Apple
   - ไปที่ **การตั้งค่าระบบ (System Settings) → ความเป็นส่วนตัวและความปลอดภัย (Privacy & Security)**
   - เลื่อนลงมาจะเห็นข้อความเกี่ยวกับ LabelSorter ถูกบล็อก กด **"เปิดโดยไม่สนใจ" (Open Anyway)**
   - ยืนยันอีกครั้งด้วย Touch ID/รหัสผ่าน
4. ครั้งต่อไปเปิดแอปได้ตามปกติจาก Applications หรือ Launchpad

**Windows:**
1. ดาวน์โหลด `LabelSorter-Windows-x.x.x.zip` จากโฟลเดอร์ที่ใช้ร่วมกัน
2. คลิกขวา → **Extract All...** ไปยังตำแหน่งที่ต้องการ (เช่น `Documents\LabelSorter`)
3. เข้าไปในโฟลเดอร์ที่แตกไฟล์แล้ว ดับเบิลคลิก `LabelSorter.exe`
4. Windows จะเตือน **"Windows protected your PC"** (SmartScreen) — เป็นเรื่องปกติสำหรับโปรแกรมที่ยังไม่ได้เซ็นใบรับรอง
   - กด **"More info"**
   - กด **"Run anyway"**
5. แนะนำให้สร้าง shortcut ของ `LabelSorter.exe` ไปวางที่ Desktop เพื่อเปิดง่ายในครั้งต่อไป

เปิดแอปแล้วรอสักครู่ เบราว์เซอร์เริ่มต้นของเครื่องจะเปิดหน้าแอปให้อัตโนมัติ

### การตั้งค่าครั้งแรก (ทำครั้งเดียวต่อเครื่อง)

1. ไปที่แท็บ **ตั้งค่า SKU**
2. ใส่พาธของโฟลเดอร์ที่ใช้ร่วมกัน (Google Drive/Dropbox) ที่เจ้าของร้านแจ้งให้ แล้วกด **เชื่อมต่อ**
3. หากยังไม่มีรหัสผ่านแอดมิน ให้เจ้าของร้านเป็นผู้ตั้งรหัสผ่านแรกในเครื่องแรก (จากนั้นจะใช้ได้ทุกเครื่องที่เชื่อมต่อโฟลเดอร์เดียวกัน)

### การใช้งานประจำวัน

1. เลือกแท็บ **Shopee** หรือ **TikTok**
2. อัปโหลดไฟล์ออเดอร์ + ไฟล์ใบปะหน้า PDF
3. กด **จัดเรียงใบปะหน้า**
4. ดาวน์โหลดผลลัพธ์ 4 ไฟล์ (PDF ใบปะหน้า / รายการออเดอร์ / สรุปจำนวนใบพัด / สรุปรวม)

ผลลัพธ์แต่ละครั้งจะถูกบันทึกไว้ในแท็บ **ประวัติ** ของเครื่องนั้นๆ โดยอัตโนมัติ (เก็บย้อนหลัง 30 วัน) —
หากต้องดาวน์โหลดไฟล์ซ้ำโดยไม่ต้องอัปโหลดใหม่ ให้เข้าแท็บนี้แทน

### เมื่อมีเวอร์ชันใหม่

แอปจะแจ้งเตือนที่ด้านบนเมื่อมีเวอร์ชันใหม่กว่าที่ใช้อยู่ ไฟล์ติดตั้งใหม่จะอยู่ในโฟลเดอร์ที่ใช้ร่วมกันเดียวกัน —
ทำตามขั้นตอน "ครั้งแรก" ด้านบนซ้ำอีกครั้งด้วยไฟล์เวอร์ชันใหม่

---

## สำหรับเจ้าของร้าน (Owner guide)

### โครงสร้างโฟลเดอร์ที่ใช้ร่วมกัน (Google Drive/Dropbox)

```
LabelSorter/                      (แชร์ให้พนักงานทุกคน)
├── sku_map.json                  SKU → ชื่อสินค้า (แก้ไขผ่านแท็บ ตั้งค่า SKU ในแอป)
├── auth.json                     รหัสผ่านแอดมิน/ประวัติ (ตั้งค่าผ่านแอปเช่นกัน อย่าแก้ไฟล์นี้ตรงๆ)
├── version.json                  {"latest": "1.2.0", "notes": "..."} — ดู version.json.template
└── installers/
    ├── LabelSorter-Mac-1.2.0.dmg
    └── LabelSorter-Windows-1.2.0.zip
```

**อย่าลบไฟล์เก่าใน `installers/` ทันที** — เก็บเวอร์ชันก่อนหน้าไว้สักพักเผื่อต้อง rollback

### Local dev / run from source
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_app.py
```

### Build (per-platform — PyInstaller cannot cross-compile)
```bash
pip install -r requirements-dev.txt
pyinstaller --clean --noconfirm LabelSorter.spec
```
Output: `dist/LabelSorter.app` (macOS) or `dist/LabelSorter/` (Windows onedir folder).

### Building via GitHub Actions (recommended)

Push a version tag and CI builds both platforms from the same commit, guaranteeing
they're never out of sync with each other:

```bash
git tag v1.2.0
git push origin v1.2.0
```

Download the two artifacts from the workflow run (Actions tab → the run → Artifacts),
then place them in the shared Drive folder's `installers/` directory and bump
`version.json`'s `"latest"` field. Staff never touch GitHub — this repo is
for building only; distribution is entirely through the shared Drive folder.

You can also trigger a build manually without tagging, via **Actions → Build desktop app →
Run workflow** — useful for a test build before cutting an official version.

**Keep in sync when bumping a version:** `sorter/version.py`'s `APP_VERSION` and
`LabelSorter.spec`'s `APP_VERSION` (used for the macOS bundle's `CFBundleShortVersionString`)
should both match the git tag.

### Releasing an update — checklist

1. Make the code change, test locally (`python run_app.py`).
2. Bump `APP_VERSION` in both `sorter/version.py` and `LabelSorter.spec`.
3. Commit, tag (`git tag vX.Y.Z`), push the tag.
4. Download the Mac + Windows artifacts from the Actions run.
5. Upload both into the shared Drive folder's `installers/`.
6. Update `version.json` in the shared folder: `{"latest": "X.Y.Z", "notes": "..."}`.
7. Staff see the update banner next time they open the app.

### Project structure
```
app.py                  Streamlit UI (Shopee / TikTok / ตั้งค่า SKU / ประวัติ tabs)
run_app.py               Desktop launcher — starts Streamlit in-process, opens the browser
LabelSorter.spec         PyInstaller build spec (onedir; see its docstring for the 3
                         non-obvious things a plain `pyinstaller run_app.py` gets wrong)
sorter/
  paths.py               resource_path() (frozen-safe bundled assets) + per-OS data dirs
  config.py               SKU map: shared folder -> local fallback -> bundled seed
  auth.py                 Admin/history passwords, same shared/local fallback pattern
  storage.py              Local batch history (save/list/purge, 30-day retention)
  version.py               App version + update check against the shared folder
  core.py                 Shared phase/group ranking, PDF reorder + safety checks
  shopee.py / tiktok.py    Platform-specific sort logic
  summary.py               จำนวนใบพัด summary transform
  exec_summary.py          สรุปรวม PDF (reportlab; bundled Thai font)
assets/fonts/             IBM Plex Sans Thai (SIL OFL) — bundled so Thai text renders
                          correctly regardless of what fonts are on a staff machine
sku_map.json              Bundled seed — copied out on first run, never read again after
.github/workflows/build.yml   CI: builds Mac .dmg + Windows .zip from a version tag
requirements.txt / requirements-dev.txt (adds pyinstaller)
```

### Notable non-obvious fixes worth knowing about

- **`sorter/core.py` `today_stamp()` avoids `strftime("%-d%b")`** — that directive is
  POSIX-only and raises `ValueError` on Windows. Every sort would have crashed there.
- **`LabelSorter.spec` needs `collect_submodules("sorter")` *and* an explicit
  `sys.path.insert(0, SPECPATH)` before calling it.** PyInstaller's static analysis only
  follows imports reachable from `run_app.py`; `app.py` (which has the real
  `from sorter import auth, config, storage, ...`) is bundled as inert data that
  Streamlit's bootstrap `exec()`s at runtime, so none of its imports are auto-discovered.
  Confirmed by inspecting the built executable's embedded PYZ archive directly — the
  `collect_submodules` call alone silently returned only `sorter.paths` (the one module
  `run_app.py` itself imports) without the sys.path fix, even though the identical call
  in a plain interactive `python3 -c` from the same directory found all 11 submodules.
