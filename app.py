"""จัดเรียงใบปะหน้า — Label Sorter Desktop App.

Staff-facing Streamlit GUI, packaged as a double-clickable Mac/Windows app:
upload the packing list + shipping-label PDF, click one button, download the
sorted PDF / order list / จำนวนใบพัด summary / executive summary. No coding,
no file paths, no terminal required.

Desktop-specific vs the hosted version: the SKU map, passwords, and update
notices live in a shared Drive/Dropbox folder (see sorter.config /
sorter.auth / sorter.version) instead of a cloud host's secrets/redeploy
mechanism, and batch history is stored locally per machine (see
sorter.storage) instead of in a cloud bucket.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from sorter import auth, config, storage, version
from sorter.core import SortIntegrityError, today_stamp
from sorter.exec_summary import build_exec_summary_pdf, build_title
from sorter.lazada import sort_lazada
from sorter.shopee import sort_shopee
from sorter.tiktok import sort_tiktok

PLATFORM_TITLES = {"shopee": "Shopee", "tiktok": "TikTok", "lazada": "Lazada"}

st.set_page_config(page_title="จัดเรียงใบปะหน้า", page_icon="🔀", layout="centered")

MAX_FILES = 2


def _too_many(files, label: str) -> bool:
    if files and len(files) > MAX_FILES:
        st.error(f"อัปโหลด{label}ได้สูงสุด {MAX_FILES} ไฟล์ / Max {MAX_FILES} files for {label}.")
        return True
    return False


def _display_summary_df(df):
    """summary_df has duplicate/blank column names by design (side-by-side
    Total | กล่อง | ใบพัด layout for the CSV export) — st.dataframe/pyarrow
    can't render duplicate column names, so build a display-only copy:
    drop the blank spacer columns and disambiguate the qty column of each
    group as '<group> จำนวน'.
    """
    keep_mask = [c != "" for c in df.columns]
    out = df.loc[:, keep_mask].copy()
    seen = set()
    new_cols = []
    for c in out.columns:
        if c in seen:
            new_cols.append(f"{c} จำนวน")
        else:
            seen.add(c)
            new_cols.append(c)
    out.columns = new_cols
    return out


def _upload_signature(order_files, pdf_files) -> tuple:
    """Identity of the currently-loaded uploads, so a result computed from an
    earlier set can be detected and discarded. Streamlit keeps a finished
    result in session_state across reruns; without this check, swapping in a
    new batch's files leaves the previous batch's download buttons on screen
    and staff can print the wrong labels.
    """
    def sig(files):
        return tuple(sorted((f.name, f.size) for f in (files or [])))

    return (sig(order_files), sig(pdf_files))


def _show_result(result, platform: str) -> None:
    st.success(f"เสร็จแล้ว — {result.num_pages} หน้า, {result.num_orders} ออเดอร์ / Done — {result.num_pages} pages, {result.num_orders} orders")

    if result.phase_summary:
        with st.expander("สรุปการจัดกลุ่ม / Group summary", expanded=True):
            for line in result.phase_summary:
                st.text(line)

    for w in result.warnings:
        st.warning(w)

    st.divider()
    stamp_suffix = "xlsx" if platform == "shopee" else "csv"
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.download_button(
            "⬇️ ใบปะหน้าเรียงแล้ว (PDF)",
            data=result.pdf_bytes,
            file_name=f"{platform.title()}_Labels_Sorted.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            f"⬇️ รายการออเดอร์ ({stamp_suffix})",
            data=result.orders_bytes,
            file_name=result.orders_filename,
            use_container_width=True,
        )
    with col3:
        st.download_button(
            "⬇️ สรุปจำนวนใบพัด (CSV)",
            data=result.summary_bytes,
            file_name="จำนวนใบพัด.csv",
            use_container_width=True,
        )
    with col4:
        batch = st.number_input(
            "รอบที่ / Batch #", min_value=1, max_value=99, value=1, step=1, key=f"batch_{platform}"
        )
        stamp = today_stamp()
        title = build_title(PLATFORM_TITLES[platform], stamp, int(batch))
        try:
            exec_pdf_bytes = build_exec_summary_pdf(result.picking_rows, result.summary_df, title)
            st.download_button(
                "⬇️ สรุปรวม (PDF)",
                data=exec_pdf_bytes,
                file_name=f"{PLATFORM_TITLES[platform]}_{stamp}_สรุปรวม.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"สร้าง PDF สรุปรวมไม่สำเร็จ / Failed to build summary PDF: {e}")

    with st.expander("ดูตารางสรุปจำนวนใบพัด / View summary table"):
        st.dataframe(_display_summary_df(result.summary_df), use_container_width=True)


def _platform_tab(platform: str, order_label: str, order_types: list[str], order_hint: str) -> None:
    session_key = f"result_{platform}"
    sig_key = f"sig_{platform}"
    saved_key = f"saved_batch_{platform}"

    order_files = st.file_uploader(
        f"1. อัปโหลด{order_label}",
        type=order_types,
        accept_multiple_files=True,
        key=f"orders_{platform}",
        help=order_hint,
    )
    pdf_files = st.file_uploader(
        "2. อัปโหลดไฟล์ใบปะหน้า (.pdf) / Upload label PDF",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"pdf_{platform}",
    )

    bad = _too_many(order_files, order_label) | _too_many(pdf_files, "ไฟล์ PDF")
    ready = bool(order_files) and bool(pdf_files) and not bad

    if st.button("🔀 จัดเรียงใบปะหน้า / Sort labels", disabled=not ready, key=f"btn_{platform}", type="primary", use_container_width=True):
        cfg = config.load_config()
        try:
            with st.spinner("กำลังจัดเรียง... / Sorting..."):
                if platform == "shopee":
                    result = sort_shopee(order_files, pdf_files, cfg)
                else:
                    result = sort_tiktok(order_files, pdf_files, cfg)
            st.session_state[session_key] = result
            st.session_state[sig_key] = _upload_signature(order_files, pdf_files)

            # Persist to local history right away (batch #1 title) so a
            # completed sort survives even if staff never touch the batch-#
            # widget or forget to download everything before closing the app.
            try:
                stamp = today_stamp()
                title = build_title(PLATFORM_TITLES[platform], stamp, 1)
                exec_pdf_bytes = build_exec_summary_pdf(result.picking_rows, result.summary_df, title)
                batch_id = storage.save_batch(
                    platform=platform,
                    result=result,
                    exec_pdf_bytes=exec_pdf_bytes,
                    batch_no=1,
                    order_filenames=[f.name for f in order_files],
                    pdf_filenames=[f.name for f in pdf_files],
                )
                st.session_state[saved_key] = batch_id
            except Exception as e:
                # History is a convenience, not the primary path — a failure
                # here must not block staff from downloading their results.
                st.session_state[saved_key] = None
                st.warning(f"บันทึกประวัติไม่สำเร็จ (ไม่กระทบการดาวน์โหลด) / Failed to save to history (downloads still work): {e}")
        except SortIntegrityError as e:
            st.session_state.pop(session_key, None)
            st.error(f"เกิดข้อผิดพลาดในการจัดเรียง / Sort integrity error: {e}")
        except Exception as e:
            st.session_state.pop(session_key, None)
            st.error(
                "ไฟล์ไม่ถูกต้อง กรุณาตรวจสอบว่าอัปโหลดไฟล์ถูกประเภทและตรงกับใบปะหน้า / "
                f"Invalid file — please check the file type and that it matches the labels. ({e})"
            )

    if session_key in st.session_state:
        current_sig = _upload_signature(order_files, pdf_files)
        if st.session_state.get(sig_key) == current_sig:
            _show_result(st.session_state[session_key], platform)
            if st.session_state.get(saved_key):
                st.caption(f"บันทึกลงประวัติแล้ว / Saved to history: {st.session_state[saved_key]}")
        elif not order_files and not pdf_files:
            # Everything was removed — nothing to show and nothing to warn about.
            st.session_state.pop(session_key, None)
            st.session_state.pop(sig_key, None)
            st.session_state.pop(saved_key, None)
        else:
            # Files changed since this result was produced. Keep the stale
            # result out of the UI (no download buttons) but leave it in
            # session_state, so this prompt persists across reruns instead of
            # flashing once and vanishing.
            st.info(
                "ไฟล์เปลี่ยนแล้ว — กรุณากด “จัดเรียงใบปะหน้า” อีกครั้ง / "
                "Files changed — please click Sort again."
            )


def _lazada_upload_signature(order_files) -> tuple:
    """Same idea as _upload_signature(), but Lazada has only one upload slot
    (no label PDF to sort)."""
    return tuple(sorted((f.name, f.size) for f in (order_files or [])))


def _show_lazada_result(result) -> None:
    st.success(
        f"เสร็จแล้ว — {result.num_rows} แถว, {result.num_orders} ออเดอร์ / "
        f"Done — {result.num_rows} rows, {result.num_orders} orders"
    )

    for w in result.warnings:
        st.warning(w)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ รายการออเดอร์ (กลับลำดับ) (xlsx)",
            data=result.orders_bytes,
            file_name=result.orders_filename,
            use_container_width=True,
        )
    with col2:
        stamp = today_stamp()
        title = build_title("Lazada", stamp, 1)
        try:
            summary_pdf_bytes = build_exec_summary_pdf(result.picking_rows, result.summary_df, title)
            st.download_button(
                "⬇️ สรุปรวม (PDF)",
                data=summary_pdf_bytes,
                file_name=f"Lazada_{stamp}_สรุปรวม.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"สร้าง PDF สรุปรวมไม่สำเร็จ / Failed to build summary PDF: {e}")

    with st.expander("ดูตารางสรุปจำนวนใบพัด / View summary table"):
        st.dataframe(_display_summary_df(result.summary_df), use_container_width=True)


def _lazada_tab() -> None:
    session_key = "result_lazada"
    sig_key = "sig_lazada"
    saved_key = "saved_batch_lazada"

    st.caption(
        "ไม่มีไฟล์ใบปะหน้าสำหรับ Lazada — อัปโหลดแค่ไฟล์ออเดอร์ ระบบจะกลับลำดับแถว "
        "(บนลงล่าง ↔ ล่างขึ้นบน) แล้วสรุปจำนวนสินค้าให้ / "
        "No label PDF for Lazada — upload just the order file; rows get reversed "
        "top-to-bottom, and you get a product-quantity summary."
    )

    order_files = st.file_uploader(
        "อัปโหลดไฟล์ออเดอร์ Lazada (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=True,
        key="orders_lazada",
        help="ไฟล์ export รายการออเดอร์จาก Lazada Seller Center",
    )

    bad = _too_many(order_files, "ไฟล์ออเดอร์ Lazada")
    ready = bool(order_files) and not bad

    if st.button(
        "📦 ประมวลผลออเดอร์ / Process orders",
        disabled=not ready, key="btn_lazada", type="primary", use_container_width=True,
    ):
        try:
            with st.spinner("กำลังประมวลผล... / Processing..."):
                result = sort_lazada(order_files, None)
            st.session_state[session_key] = result
            st.session_state[sig_key] = _lazada_upload_signature(order_files)

            try:
                stamp = today_stamp()
                title = build_title("Lazada", stamp, 1)
                summary_pdf_bytes = build_exec_summary_pdf(result.picking_rows, result.summary_df, title)
                batch_id = storage.save_lazada_batch(
                    result=result,
                    summary_pdf_bytes=summary_pdf_bytes,
                    order_filenames=[f.name for f in order_files],
                )
                st.session_state[saved_key] = batch_id
            except Exception as e:
                st.session_state[saved_key] = None
                st.warning(
                    "บันทึกประวัติไม่สำเร็จ (ไม่กระทบการดาวน์โหลด) / "
                    f"Failed to save to history (downloads still work): {e}"
                )
        except Exception as e:
            st.session_state.pop(session_key, None)
            st.error(
                "ไฟล์ไม่ถูกต้อง กรุณาตรวจสอบว่าอัปโหลดไฟล์ถูกประเภทและมีคอลัมน์ "
                "orderNumber/sellerSku / Invalid file — please check the file type "
                f"and that it has orderNumber/sellerSku columns. ({e})"
            )

    if session_key in st.session_state:
        current_sig = _lazada_upload_signature(order_files)
        if st.session_state.get(sig_key) == current_sig:
            _show_lazada_result(st.session_state[session_key])
            if st.session_state.get(saved_key):
                st.caption(f"บันทึกลงประวัติแล้ว / Saved to history: {st.session_state[saved_key]}")
        elif not order_files:
            st.session_state.pop(session_key, None)
            st.session_state.pop(sig_key, None)
            st.session_state.pop(saved_key, None)
        else:
            st.info(
                "ไฟล์เปลี่ยนแล้ว — กรุณากด “ประมวลผลออเดอร์” อีกครั้ง / "
                "Files changed — please click Process again."
            )


def _admin_tab() -> None:
    st.subheader("ตั้งค่า / Settings")

    # --- shared folder: always visible, no password. This is how a fresh
    # machine bootstraps everything else (SKU map, passwords, updates) ---
    st.markdown("#### โฟลเดอร์ที่ใช้ร่วมกัน / Shared folder")
    st.caption(
        "โฟลเดอร์ Google Drive/Dropbox เดียวกันสำหรับทุกเครื่อง ใช้เก็บ SKU, รหัสผ่าน, "
        "และไฟล์ติดตั้งเวอร์ชันใหม่ / The same Drive/Dropbox folder on every machine — "
        "holds the SKU map, passwords, and update installers."
    )

    active_path, source = config.get_sku_map_status()
    status_text = {
        "shared": "✅ เชื่อมต่อโฟลเดอร์ที่ใช้ร่วมกันแล้ว / Connected to the shared folder",
        "local": "⚠️ ยังไม่ได้เชื่อมต่อ — ใช้ไฟล์ในเครื่องนี้เท่านั้น / Not connected — using this machine's local copy only",
        "seeded": "⚠️ เพิ่งสร้างไฟล์ตั้งต้นในเครื่องนี้ / Just created a fresh local copy on this machine",
    }[source]
    st.caption(status_text)
    st.text(f"ไฟล์ปัจจุบัน / Current file: {active_path}")

    current_shared = config.get_settings().get("shared_sku_map_path", "")
    folder_default = str(Path(current_shared).parent) if current_shared else ""
    folder_input = st.text_input(
        "พาธโฟลเดอร์ที่ใช้ร่วมกัน / Shared folder path",
        value=folder_default,
        key="shared_folder_input",
        placeholder=r"เช่น / e.g. C:\Users\Name\Google Drive\LabelSorter",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔗 เชื่อมต่อ / Connect", use_container_width=True):
            if folder_input.strip():
                try:
                    config.set_shared_sku_map_path(folder_input.strip())
                    st.success("เชื่อมต่อแล้ว / Connected.")
                    st.rerun()
                except Exception as e:
                    st.error(f"เชื่อมต่อไม่สำเร็จ / Failed to connect: {e}")
            else:
                st.error("กรุณาระบุพาธโฟลเดอร์ / Please enter a folder path")
    with col_b:
        if source == "shared" and st.button("✂️ ยกเลิกการเชื่อมต่อ / Disconnect", use_container_width=True):
            config.clear_shared_sku_map_path()
            st.rerun()

    st.divider()

    # --- password-gated section ---
    admin_password = auth.get_admin_password()

    if not admin_password:
        st.info(
            "ยังไม่ได้ตั้งรหัสผ่านแอดมิน — ตั้งค่าครั้งแรกได้เลย (แนะนำให้เชื่อมต่อโฟลเดอร์ที่ใช้ร่วมกันก่อน "
            "เพื่อให้รหัสผ่านนี้ใช้ได้ทุกเครื่อง) / No admin password set yet — set one now "
            "(connect the shared folder first so this password works on every machine)."
        )
        new_pw = st.text_input("ตั้งรหัสผ่านแอดมิน / Set admin password", type="password", key="bootstrap_pw")
        if st.button("บันทึกรหัสผ่าน / Save password"):
            if not new_pw:
                st.error("กรุณากรอกรหัสผ่าน / Please enter a password")
            else:
                try:
                    auth.set_admin_password(new_pw)
                    st.success("ตั้งรหัสผ่านแล้ว / Password set.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        return

    if not st.session_state.get("admin_ok"):
        pw = st.text_input("รหัสผ่าน / Password", type="password", key="admin_pw_input")
        if st.button("เข้าสู่ระบบ / Log in"):
            if pw == admin_password:
                st.session_state["admin_ok"] = True
                st.rerun()
            else:
                st.error("รหัสผ่านไม่ถูกต้อง / Wrong password")
        return

    st.markdown("#### ตั้งค่า SKU / SKU settings")
    cfg = config.load_config()
    rows = [{"SKU": sku, "ชื่อสินค้า": label} for sku, label in sorted(cfg.sku_map.items())]
    edited = st.data_editor(rows, num_rows="dynamic", use_container_width=True, key="sku_editor")

    if st.button("💾 บันทึก / Save"):
        skus = [str(r.get("SKU", "")).strip() for r in edited]
        if any(not s for s in skus):
            st.error("มี SKU ที่ว่างเปล่า กรุณากรอกให้ครบ / Some SKU fields are blank.")
        elif len(skus) != len(set(skus)):
            st.error("มี SKU ซ้ำกัน กรุณาแก้ไข / Duplicate SKUs found.")
        else:
            new_map = {str(r["SKU"]).strip(): str(r["ชื่อสินค้า"]).strip() for r in edited}
            config.save_sku_map(new_map)
            note = " ทุกเครื่องที่เชื่อมต่อโฟลเดอร์นี้จะเห็นการเปลี่ยนแปลง / All machines connected to this folder will see the change." if source == "shared" else ""
            st.success("บันทึกแล้ว / Saved." + note)

    st.divider()
    st.markdown("#### เปลี่ยนรหัสผ่าน / Change passwords")
    col1, col2 = st.columns(2)
    with col1:
        new_admin_pw = st.text_input("รหัสผ่านแอดมินใหม่ / New admin password", type="password", key="new_admin_pw")
        if st.button("บันทึกรหัสผ่านแอดมิน / Save admin password"):
            if new_admin_pw:
                try:
                    auth.set_admin_password(new_admin_pw)
                    st.success("บันทึกแล้ว / Saved.")
                except Exception as e:
                    st.error(str(e))
    with col2:
        new_hist_pw = st.text_input("รหัสผ่านหน้าประวัติใหม่ / New history password", type="password", key="new_hist_pw")
        if st.button("บันทึกรหัสผ่านประวัติ / Save history password"):
            if new_hist_pw:
                try:
                    auth.set_history_password(new_hist_pw)
                    st.success("บันทึกแล้ว / Saved.")
                except Exception as e:
                    st.error(str(e))

    if st.button("ออกจากระบบ / Log out"):
        st.session_state["admin_ok"] = False
        st.rerun()


def _history_tab() -> None:
    st.subheader("ประวัติ / History")
    st.caption("เก็บย้อนหลัง 30 วัน (เฉพาะเครื่องนี้) / Kept for 30 days (this machine only)")

    history_password = auth.get_history_password()
    if not history_password:
        st.info(
            "ยังไม่ได้ตั้งรหัสผ่าน — ไปที่แท็บ ตั้งค่า SKU เพื่อตั้งรหัสผ่านแอดมินก่อน / "
            "No password set yet — set an admin password in the ตั้งค่า SKU tab first."
        )
        return

    if not st.session_state.get("history_ok"):
        pw = st.text_input("รหัสผ่าน / Password", type="password", key="history_pw_input")
        if st.button("เข้าสู่ระบบ / Log in", key="history_login_btn"):
            if pw == history_password:
                st.session_state["history_ok"] = True
                st.rerun()
            else:
                st.error("รหัสผ่านไม่ถูกต้อง / Wrong password")
        return

    batches = storage.list_batches(days=30)
    if not batches:
        st.info("ยังไม่มีประวัติ / No batches yet.")
    for meta in batches:
        platform = meta["platform"]
        if platform == "lazada":
            # No label PDF for Lazada (see sorter.storage.save_lazada_batch) —
            # "pages" has no meaning here, show order count only.
            label = f"{meta['created_at'][:16].replace('T', ' ')} — Lazada — {meta['num_orders']} ออเดอร์ / orders"
        else:
            label = f"{meta['created_at'][:16].replace('T', ' ')} — {PLATFORM_TITLES[platform]} — {meta['num_pages']} หน้า / pages, {meta['num_orders']} ออเดอร์ / orders"
        with st.expander(label):
            source_files = meta["order_filenames"] + meta.get("pdf_filenames", [])
            st.caption("ไฟล์ต้นฉบับ / Source files: " + ", ".join(source_files))
            for w in meta.get("warnings", []):
                st.warning(w)

            if platform == "lazada":
                bcol1, bcol2 = st.columns(2)
                with bcol1:
                    st.download_button(
                        "⬇️ รายการออเดอร์", data=storage.load_batch_file(meta["batch_id"], "orders"),
                        file_name=f"orders_sorted.{meta['orders_ext']}",
                        key=f"h_orders_{meta['batch_id']}", use_container_width=True,
                    )
                with bcol2:
                    st.download_button(
                        "⬇️ สรุปรวม", data=storage.load_batch_file(meta["batch_id"], "exec_summary"),
                        file_name="สรุปรวม.pdf", mime="application/pdf",
                        key=f"h_exec_{meta['batch_id']}", use_container_width=True,
                    )
                continue

            bcol1, bcol2, bcol3, bcol4 = st.columns(4)
            with bcol1:
                st.download_button(
                    "⬇️ PDF ใบปะหน้า", data=storage.load_batch_file(meta["batch_id"], "labels"),
                    file_name="labels_sorted.pdf", mime="application/pdf",
                    key=f"h_labels_{meta['batch_id']}", use_container_width=True,
                )
            with bcol2:
                st.download_button(
                    "⬇️ รายการออเดอร์", data=storage.load_batch_file(meta["batch_id"], "orders"),
                    file_name=f"orders_sorted.{meta['orders_ext']}",
                    key=f"h_orders_{meta['batch_id']}", use_container_width=True,
                )
            with bcol3:
                st.download_button(
                    "⬇️ สรุปจำนวนใบพัด", data=storage.load_batch_file(meta["batch_id"], "summary"),
                    file_name="จำนวนใบพัด.csv",
                    key=f"h_summary_{meta['batch_id']}", use_container_width=True,
                )
            with bcol4:
                st.download_button(
                    "⬇️ สรุปรวม", data=storage.load_batch_file(meta["batch_id"], "exec_summary"),
                    file_name="สรุปรวม.pdf", mime="application/pdf",
                    key=f"h_exec_{meta['batch_id']}", use_container_width=True,
                )

    if st.button("ออกจากระบบ / Log out", key="history_logout_btn"):
        st.session_state["history_ok"] = False
        st.rerun()


def main() -> None:
    if not st.session_state.get("_purged_this_session"):
        storage.purge_expired(days=30)
        st.session_state["_purged_this_session"] = True

    st.title("🔀 จัดเรียงใบปะหน้า")
    st.caption("อัปโหลดไฟล์ → กดจัดเรียง → ดาวน์โหลด / Upload files → click Sort → download")

    update = version.check_for_update()
    if update:
        st.warning(
            f"มีเวอร์ชันใหม่ {update['latest']} (ตอนนี้ {version.APP_VERSION}) — "
            f"ไฟล์ติดตั้งอยู่ในโฟลเดอร์ที่ใช้ร่วมกัน / A newer version {update['latest']} "
            f"is available (you have {version.APP_VERSION}) — the installer is in the shared folder."
            + (f"\n\n{update['notes']}" if update["notes"] else "")
        )

    tab_shopee, tab_tiktok, tab_lazada, tab_admin, tab_history = st.tabs(
        ["Shopee", "TikTok", "Lazada", "ตั้งค่า SKU", "ประวัติ"]
    )

    with tab_shopee:
        _platform_tab(
            "shopee",
            order_label="Packing List (.xlsx)",
            order_types=["xlsx"],
            order_hint="ไฟล์ Packing List จาก Shopee Seller Centre",
        )

    with tab_tiktok:
        _platform_tab(
            "tiktok",
            order_label="ไฟล์ออเดอร์ To Ship (.csv)",
            order_types=["csv"],
            order_hint='ไฟล์ CSV "To Ship" จาก TikTok Shop Seller Centre',
        )

    with tab_lazada:
        _lazada_tab()

    with tab_admin:
        _admin_tab()

    with tab_history:
        _history_tab()

    st.divider()
    st.caption(f"เวอร์ชัน / Version {version.APP_VERSION}")


if __name__ == "__main__":
    main()
