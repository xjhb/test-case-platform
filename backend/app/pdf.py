"""测试报告 PDF 渲染(纯 reportlab,不依赖浏览器或 wkhtmltopdf)。

中文字体优先内嵌系统 TTF,保证收件方无需安装字体即可打开;
找不到时退回 PDF 内置的 CID 字体(STSong-Light)。
"""

import html
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_CANDIDATES = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]
CID_FALLBACK = "STSong-Light"

_font_cache: str | None = None

HEADER_BG = colors.HexColor("#1E3C72")
ROW_BG = colors.HexColor("#F5F7FA")
GRID = colors.HexColor("#C9CFDA")


def cjk_font() -> str:
    global _font_cache
    if _font_cache:
        return _font_cache
    for path in FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("ReportCJK", path))
            _font_cache = "ReportCJK"
            return _font_cache
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont(CID_FALLBACK))
    _font_cache = CID_FALLBACK
    return _font_cache


def _styles():
    f = cjk_font()
    return {
        "title": ParagraphStyle("t", fontName=f, fontSize=17, leading=22, alignment=1, textColor=HEADER_BG),
        "subtitle": ParagraphStyle("s", fontName=f, fontSize=9.5, leading=13, alignment=1, textColor=colors.HexColor("#6B7280")),
        "h2": ParagraphStyle("h2", fontName=f, fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4, textColor=HEADER_BG),
        "body": ParagraphStyle("b", fontName=f, fontSize=9.5, leading=14),
        "cell": ParagraphStyle("c", fontName=f, fontSize=8.5, leading=11),
    }


def _grid_style(header_rows: int = 1):
    f = cjk_font()
    style = [
        ("FONTNAME", (0, 0), (-1, -1), f),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, ROW_BG]),
    ]
    return style


def _txt(value) -> str:
    """单元格文本转义:报告内容来自用户输入,不能当作标签解析"""
    s = html.escape("" if value is None else str(value), quote=False)
    return s.replace("\n", "<br/>")


def build_report_pdf(
    *,
    title: str,
    subtitle: str = "",
    info_rows: list[list[str]] | None = None,
    sections: list[dict] | None = None,
    conclusion: str = "",
    footer: str = "",
    landscape: bool = False,
) -> bytes:
    """sections: [{name, columns:[...], rows:[[...]], widths:[mm...], align_right:[列号]}]"""
    st = _styles()
    page = (A4[1], A4[0]) if landscape else A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=page,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=title,
    )
    usable = page[0] - 28 * mm

    def footer_pdf(canvas, _doc):
        canvas.saveState()
        canvas.setFont(cjk_font(), 7.5)
        canvas.setFillColor(colors.HexColor("#8A94A6"))
        canvas.drawString(14 * mm, 9 * mm, footer)
        canvas.drawRightString(page[0] - 14 * mm, 9 * mm, f"第 {_doc.page} 页")
        canvas.restoreState()

    story = [Paragraph(_txt(title), st["title"])]
    if subtitle:
        story.append(Spacer(1, 4))
        story.append(Paragraph(_txt(subtitle), st["subtitle"]))
    story.append(Spacer(1, 10))

    if info_rows:
        t = Table([[_txt(c) for c in row] for row in info_rows],
                  colWidths=[usable * 0.18, usable * 0.32, usable * 0.18, usable * 0.32])
        f = cjk_font()
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), f),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4B5563")),
            ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#4B5563")),
            ("GRID", (0, 0), (-1, -1), 0.4, GRID),
            ("BACKGROUND", (0, 0), (0, -1), ROW_BG),
            ("BACKGROUND", (2, 0), (2, -1), ROW_BG),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    for sec in sections or []:
        story.append(Paragraph(_txt(sec["name"]), st["h2"]))
        columns = [[Paragraph(_txt(c), st["cell"]) for c in sec["columns"]]]
        rows = [[Paragraph(_txt(c), st["cell"]) for c in r] for r in sec["rows"]]
        widths = sec.get("widths")
        if widths:
            total = sum(widths)
            col_w = [usable * (w / total) for w in widths]
        else:
            col_w = [usable / max(1, len(sec["columns"]))] * len(sec["columns"])
        data = columns + rows
        t = Table(data, colWidths=col_w, repeatRows=1)
        style = _grid_style(header_rows=1)
        for col in sec.get("align_right", []):
            style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
        t.setStyle(TableStyle(style))
        story.append(t)

    if conclusion:
        story.append(Paragraph("结论与建议", st["h2"]))
        story.append(Paragraph(_txt(conclusion), st["body"]))

    doc.build(story, onFirstPage=footer_pdf, onLaterPages=footer_pdf)
    return buf.getvalue()
