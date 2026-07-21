"""Executive-summary PDF — a numbered picking list plus the จำนวนใบพัด
summary tables, matching the layout of the operator's existing manual report
(one row per label in sorted order, highlighted by business rule, followed by
the Total / กล่อง / ใบพัด group tables).

Layout: 3 fixed-width columns, 60 picking-list rows per column (up to 150
rows across columns 1-2 and the start of column 3), with the จำนวนใบพัด
summary tables flowing directly after the last list row in whichever column
has room — landing on the same single page for the common case (<=150 rows).
If the picking list is longer, Platypus's frame-flow automatically continues
the list (and then the summary tables) onto further pages using the same
3-column template — nothing is ever dropped, it just stops being one page.

Built with reportlab (pure Python, no system dependencies) so it deploys
safely on Streamlit Community Cloud and inside a frozen desktop build alike.
Thai text uses the bundled IBM Plex Thai font (SIL Open Font License) — the
environment's fonts can't be relied on.

Highlight rule (business definition, not cosmetic):
  no highlight -> Phase A, single SKU, qty = 1
  green        -> Phase B, single SKU, qty >= 2
  yellow       -> Phase C, one order with multiple distinct SKU rows
"""
from __future__ import annotations

import io

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    KeepTogether,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .paths import resource_path

_fonts_registered = False

GREEN = colors.HexColor("#c6efce")
YELLOW = colors.HexColor("#fff2cc")
HEADER_BG = colors.HexColor("#4472c4")
GRID_COLOR = colors.HexColor("#cccccc")

ROWS_PER_COLUMN = 60
N_COLUMNS = 3


def _register_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    font_dir = resource_path("assets", "fonts")
    pdfmetrics.registerFont(TTFont("PlexThai", str(font_dir / "PlexThai-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("PlexThai-Bold", str(font_dir / "PlexThai-SemiBold.ttf")))
    _fonts_registered = True


def _extract_group_tables(summary_df: pd.DataFrame) -> list[tuple[str, list[tuple[str, object]]]]:
    """summary_df is laid out as Total(label,qty) | spacer | กล่อง(label,qty) |
    spacer | ใบพัด(label,qty) — see sorter.summary.build_report. Pull out the
    three (name, [(label, qty), ...]) groups by fixed column position.
    """
    groups = []
    idx = 0
    for name in ("Total", "กล่อง", "ใบพัด"):
        label_col = summary_df.iloc[:, idx]
        qty_col = summary_df.iloc[:, idx + 1]
        rows = [(str(l), q) for l, q in zip(label_col, qty_col) if str(l).strip() != ""]
        groups.append((name, rows))
        idx += 3
    return groups


def build_title(platform_title: str, date_stamp: str, batch: int) -> str:
    title = f"{platform_title} {date_stamp}"
    if batch and batch != 1:
        title += f" #{batch}"
    return title


def build_exec_summary_pdf(picking_rows: list[dict], summary_df: pd.DataFrame, title: str) -> bytes:
    _register_fonts()
    buf = io.BytesIO()

    page_w, page_h = A4
    margin = 10 * mm
    gutter = 5 * mm
    header_h = 12 * mm

    col_w = (page_w - 2 * margin - (N_COLUMNS - 1) * gutter) / N_COLUMNS
    content_h = page_h - 2 * margin - header_h

    frames = [
        Frame(margin + i * (col_w + gutter), margin, col_w, content_h, id=f"col{i}", showBoundary=0)
        for i in range(N_COLUMNS)
    ]

    def draw_header(canvas, _doc):
        canvas.saveState()
        canvas.setFont("PlexThai-Bold", 14)
        canvas.drawCentredString(page_w / 2, page_h - margin - 5 * mm, title)
        canvas.restoreState()

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        pageTemplates=[PageTemplate(id="Main", frames=frames, onPage=draw_header)],
    )

    # All cells use Paragraph (never a raw string) so row height is governed
    # uniformly by these styles' `leading` — plain strings in a reportlab
    # Table cell instead size to the font's native ascent/descent, which for
    # this font renders visibly taller and silently breaks the fixed
    # 60-rows-per-column budget.
    cell_style = ParagraphStyle("cell", fontName="PlexThai-Bold", fontSize=8.5, leading=9.8)
    num_style = ParagraphStyle("num", parent=cell_style, alignment=TA_RIGHT)
    header_style = ParagraphStyle("header", fontName="PlexThai-Bold", fontSize=9, leading=10.6, textColor=colors.white)
    header_num_style = ParagraphStyle("header_num", parent=header_style, alignment=TA_RIGHT)
    section_style = ParagraphStyle(
        "section", fontName="PlexThai-Bold", fontSize=11, leading=14.3, spaceBefore=4, spaceAfter=3
    )

    num_w, qty_w = 7.5 * mm, 12 * mm
    label_w = col_w - num_w - qty_w

    def make_list_table(chunk: list[dict], start_num: int) -> Table:
        data = [[Paragraph("#", header_num_style), Paragraph("สินค้า", header_style), Paragraph("จำนวน", header_num_style)]]
        row_highlight_styles = []
        for offset, row in enumerate(chunk):
            data.append(
                [
                    Paragraph(str(start_num + offset), num_style),
                    Paragraph(str(row["label"]), cell_style),
                    Paragraph(str(row["qty"]), num_style),
                ]
            )
            r = offset + 1
            if row["highlight"] == "green":
                row_highlight_styles.append(("BACKGROUND", (0, r), (-1, r), GREEN))
            elif row["highlight"] == "yellow":
                # Only one cell per row marks a MIXED-order group: the first
                # line item's "#" cell (col 0), every other line item's
                # "qty" cell (col 2) — not the whole row.
                col = 0 if row.get("highlight_cell") == "num" else 2
                row_highlight_styles.append(("BACKGROUND", (col, r), (col, r), YELLOW))

        t = Table(data, colWidths=[num_w, label_w, qty_w], repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                    ("GRID", (0, 0), (-1, -1), 0.3, GRID_COLOR),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.75),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.75),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
                + row_highlight_styles
            )
        )
        return t

    story = []

    # --- numbered picking list: fixed 60-row columns, 3 per page ---
    n = len(picking_rows)
    pos = 0
    first_chunk = True
    while pos < n or (n == 0 and first_chunk):
        chunk = picking_rows[pos : pos + ROWS_PER_COLUMN]
        if not first_chunk:
            story.append(FrameBreak())
        if chunk:
            story.append(make_list_table(chunk, pos + 1))
        else:
            story.append(Paragraph("ไม่มีรายการ / No items", cell_style))
        pos += ROWS_PER_COLUMN
        first_chunk = False

    # --- จำนวนใบพัด summary tables, flowing right after the list in
    # whichever column has room (same page if the list is <=150 rows;
    # otherwise it naturally continues onto the next page) ---
    story.append(Spacer(1, 4 * mm))
    for name, rows in _extract_group_tables(summary_df):
        data = [[Paragraph(name, header_style), Paragraph("จำนวน", header_num_style)]] + [
            [Paragraph(label, cell_style), Paragraph(str(qty), num_style)] for label, qty in rows
        ]
        t = Table(data, colWidths=[col_w - 15 * mm, 15 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                    ("GRID", (0, 0), (-1, -1), 0.3, GRID_COLOR),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ]
            )
        )
        # Small tables (a handful of rows) — keep the title+table together
        # as one unit so a page/column split never orphans the header.
        story.append(KeepTogether([Paragraph(name, section_style), t]))
        story.append(Spacer(1, 4 * mm))

    doc.build(story)
    return buf.getvalue()


def build_group_summary_pdf(summary_df: pd.DataFrame, title: str) -> bytes:
    """Just the Total / กล่อง / ใบพัด tables, no numbered picking list.

    For platforms with no shipping-label PDF to enumerate (Lazada: a plain
    row-reversed order list, not a picking sequence) — same tables and
    styling as build_exec_summary_pdf(), single column since there's no
    3-column picking-list layout to share the page with.
    """
    _register_fonts()
    buf = io.BytesIO()

    page_w, page_h = A4
    margin = 15 * mm

    cell_style = ParagraphStyle("cell", fontName="PlexThai-Bold", fontSize=10, leading=12)
    num_style = ParagraphStyle("num", parent=cell_style, alignment=TA_RIGHT)
    header_style = ParagraphStyle("header", fontName="PlexThai-Bold", fontSize=10.5, leading=12.5, textColor=colors.white)
    header_num_style = ParagraphStyle("header_num", parent=header_style, alignment=TA_RIGHT)
    section_style = ParagraphStyle(
        "section", fontName="PlexThai-Bold", fontSize=13, leading=16, spaceBefore=6, spaceAfter=4
    )
    title_style = ParagraphStyle("title", fontName="PlexThai-Bold", fontSize=16, leading=20, alignment=1, spaceAfter=10)

    table_w = page_w - 2 * margin

    story = [Paragraph(title, title_style)]
    for name, rows in _extract_group_tables(summary_df):
        data = [[Paragraph(name, header_style), Paragraph("จำนวน", header_num_style)]] + [
            [Paragraph(label, cell_style), Paragraph(str(qty), num_style)] for label, qty in rows
        ]
        t = Table(data, colWidths=[table_w - 30 * mm, 30 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                    ("GRID", (0, 0), (-1, -1), 0.4, GRID_COLOR),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(KeepTogether([Paragraph(name, section_style), t]))
        story.append(Spacer(1, 6 * mm))

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=margin, bottomMargin=margin, leftMargin=margin, rightMargin=margin)
    doc.build(story)
    return buf.getvalue()
