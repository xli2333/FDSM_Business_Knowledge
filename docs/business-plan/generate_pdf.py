"""
Generate a professional PDF from the BP markdown.
Uses fpdf2 with Chinese font support.
V6: larger fonts, bold cover, better layout, revenue forecast.
"""
import re
from fpdf import FPDF

FONT_PATH = "C:/Windows/Fonts/NotoSansSC-VF.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/simhei.ttf"
INPUT_MD = "BP.md"
OUTPUT_PDF = "复旦管院智识库_商业计划书.pdf"

FUDAN_BLUE = (13, 7, 131)
FUDAN_ORANGE = (234, 107, 0)
FUDAN_DARK = (10, 5, 96)
WHITE = (255, 255, 255)
LIGHT_GRAY = (245, 245, 250)
TEXT_DARK = (30, 30, 40)
TEXT_MED = (80, 80, 100)

EMOJI_MAP = {"\u2705": "[OK]", "\U0001f504": "[>>]", "\U0001f4cb": "[..]", "\U0001f52e": "[**]"}


def clean_emoji(text):
    for e, r in EMOJI_MAP.items():
        text = text.replace(e, r)
    return text


def strip_md(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"&nbsp;", " ", text)
    return clean_emoji(text)


class BPReport(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("NotoSC", "", FONT_PATH)
        self.add_font("SimHei", "", FONT_BOLD_PATH)
        self.set_auto_page_break(auto=True, margin=16)

    def header(self):
        if self.page_no() > 1:
            self.set_font("NotoSC", "", 8)
            self.set_text_color(*TEXT_MED)
            self.cell(0, 5, "复旦管院智识库 — 商业计划书", align="L")
            self.cell(0, 5, f"第 {self.page_no()} 页", align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*FUDAN_BLUE)
            self.set_line_width(0.3)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_font("NotoSC", "", 7.5)
        self.set_text_color(*TEXT_MED)
        self.cell(0, 6, "KDCC · 2026年4月 · 机密文件", align="C")

    def add_cover_page(self):
        self.add_page()
        self.set_fill_color(*FUDAN_DARK)
        self.rect(0, 0, 210, 297, "F")

        # Orange accent
        self.set_fill_color(*FUDAN_ORANGE)
        self.rect(20, 70, 70, 3.5, "F")

        # Main title — LARGE and BOLD
        self.set_y(82)
        self.set_font("SimHei", "", 44)
        self.set_text_color(*WHITE)
        self.cell(0, 24, "复旦管院智识库", align="L", new_x="LMARGIN", new_y="NEXT")

        # Subtitle — bold
        self.set_font("SimHei", "", 22)
        self.set_text_color(220, 220, 240)
        self.cell(0, 14, "十年商业智慧，一键触达", align="L", new_x="LMARGIN", new_y="NEXT")

        self.ln(12)
        # Description — larger
        self.set_font("SimHei", "", 14)
        self.set_text_color(190, 190, 210)
        self.cell(0, 9, "AI 驱动的新一代商业知识平台", align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font("NotoSC", "", 12)
        self.set_text_color(170, 170, 195)
        self.cell(0, 8, "将复旦管理学院十余年深度商业知识内容", align="L", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "转化为可检索、可对话、可发现的智识资产", align="L", new_x="LMARGIN", new_y="NEXT")

        # Bottom info — larger
        self.set_y(218)
        self.set_draw_color(100, 100, 140)
        self.set_line_width(0.2)
        self.line(20, 218, 190, 218)
        self.ln(8)

        self.set_font("SimHei", "", 13)
        for label, value in [("团队", "KDCC"), ("日期", "2026 年 4 月"), ("面向", "复旦大学管理学院")]:
            self.set_text_color(160, 160, 185)
            self.cell(35, 11, label, align="L")
            self.set_text_color(*WHITE)
            self.cell(0, 11, value, align="L", new_x="LMARGIN", new_y="NEXT")

    def add_section_page(self, title, content_lines, force_new_page=True):
        if force_new_page:
            self.add_page()
        self.set_text_color(*TEXT_DARK)

        # Ensure title + some content stay on same page (need at least 50mm)
        if self.get_y() + 50 > self.h - 16:
            self.add_page()

        self.set_fill_color(*FUDAN_ORANGE)
        self.rect(self.l_margin, self.get_y(), 45, 2.5, "F")
        self.ln(5)
        self.set_font("SimHei", "", 24)
        self.set_text_color(*FUDAN_DARK)
        self.cell(0, 14, clean_emoji(title), align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

        self._render(content_lines)

    def _render(self, lines):
        i = 0
        in_code = False
        code_lines = []
        in_table = False
        table_rows = []

        while i < len(lines):
            line = lines[i]

            if line.strip().startswith("```"):
                if in_code:
                    self._code(code_lines)
                    code_lines = []
                    in_code = False
                else:
                    in_code = True
                i += 1
                continue
            if in_code:
                code_lines.append(line)
                i += 1
                continue

            if "|" in line and line.strip().startswith("|"):
                if not in_table:
                    in_table = True
                    table_rows = []
                if re.match(r"^\|[\s\-:|]+\|$", line.strip()):
                    i += 1
                    continue
                cells = [c.strip() for c in line.strip().split("|")[1:-1]]
                table_rows.append(cells)
                if i + 1 >= len(lines) or not lines[i + 1].strip().startswith("|"):
                    self._table(table_rows)
                    in_table = False
                    table_rows = []
                i += 1
                continue

            s = line.strip()

            if not s or s in ["<br>", "<br><br>", "<br><br><br>", "---"]:
                self.ln(2)
                i += 1
                continue
            if s.startswith("<") or s.startswith("<!--"):
                i += 1
                continue

            # H3
            if s.startswith("### "):
                text = strip_md(s[4:])
                self.ln(3)
                self.set_font("SimHei", "", 15)
                self.set_text_color(*FUDAN_BLUE)
                self.multi_cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
                self.set_text_color(*TEXT_DARK)
                self.ln(2)
                i += 1
                continue

            # H4
            if s.startswith("#### "):
                text = strip_md(s[5:])
                self.ln(2)
                self.set_font("SimHei", "", 13)
                self.set_text_color(*FUDAN_DARK)
                self.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
                self.set_text_color(*TEXT_DARK)
                self.ln(1.5)
                i += 1
                continue

            # Blockquote
            if s.startswith("> ") or s == ">":
                parts = []
                while i < len(lines):
                    ls = lines[i].strip()
                    if ls.startswith("> "):
                        parts.append(strip_md(ls[2:]))
                        i += 1
                    elif ls == ">":
                        i += 1
                    else:
                        break
                qt = " ".join(p for p in parts if p)
                if qt:
                    y = self.get_y()
                    self.set_fill_color(*FUDAN_ORANGE)
                    self.rect(self.l_margin, y, 2, 9, "F")
                    self.set_x(self.l_margin + 5)
                    self.set_font("NotoSC", "", 11)
                    self.set_text_color(*TEXT_MED)
                    self.multi_cell(self.w - self.l_margin - self.r_margin - 5, 6,
                                    qt, new_x="LMARGIN", new_y="NEXT", align="L")
                    self.set_text_color(*TEXT_DARK)
                    self.ln(2)
                continue

            # Bullet
            if s.startswith("- ") or s.startswith("* "):
                text = strip_md(s[2:])
                self.set_font("NotoSC", "", 11)
                self.cell(6, 6, "·")
                self.multi_cell(self.w - self.l_margin - self.r_margin - 6, 6,
                                text, new_x="LMARGIN", new_y="NEXT", align="L")
                self.ln(0.5)
                i += 1
                continue

            # Bold standalone
            if s.startswith("**") and s.endswith("**"):
                text = clean_emoji(s[2:-2])
                self.set_font("SimHei", "", 12)
                self.multi_cell(0, 6.5, text, new_x="LMARGIN", new_y="NEXT")
                self.set_font("NotoSC", "", 11)
                self.ln(0.5)
                i += 1
                continue

            # Regular text
            text = strip_md(s)
            self.set_font("NotoSC", "", 11)
            self.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT", align="L")
            self.ln(0.5)
            i += 1

    def _table(self, rows):
        if not rows:
            return
        nc = max(len(r) for r in rows)
        if nc == 0:
            return
        uw = self.w - self.l_margin - self.r_margin

        cl = []
        for ci in range(nc):
            mx = 0
            for r in rows:
                if ci < len(r):
                    mx = max(mx, len(strip_md(r[ci])))
            cl.append(max(mx, 2))
        total = sum(cl)
        cw = [max(12, l / total * uw) for l in cl]
        total = sum(cw)
        cw = [w / total * uw for w in cw]

        for ri, row in enumerate(rows):
            is_h = (ri == 0)
            if is_h:
                self.set_fill_color(*FUDAN_DARK)
                self.set_text_color(*WHITE)
                self.set_font("SimHei", "", 10)
            else:
                self.set_fill_color(*(LIGHT_GRAY if ri % 2 == 0 else WHITE))
                self.set_text_color(*TEXT_DARK)
                self.set_font("NotoSC", "", 10)

            ct = []
            ml = 1
            for ci in range(nc):
                text = strip_md(row[ci] if ci < len(row) else "")
                ct.append(text)
                cpl = max(1, int(cw[ci] / 2.5))
                nl = max(1, (len(text) + cpl - 1) // cpl)
                ml = max(ml, nl)

            rh = max(6, ml * 5.5 + 1)
            rh = min(rh, 28)

            if self.get_y() + rh > self.h - 16:
                self.add_page()

            x0, y0 = self.get_x(), self.get_y()
            for ci in range(nc):
                self.set_xy(x0 + sum(cw[:ci]), y0)
                self.multi_cell(cw[ci], 5.5, ct[ci], border=0, fill=True,
                                new_x="RIGHT", new_y="TOP", align="L")
            self.set_xy(x0, y0 + rh)

        self.set_text_color(*TEXT_DARK)
        self.ln(2.5)

    def _code(self, lines):
        self.set_fill_color(240, 240, 245)
        self.set_font("NotoSC", "", 9.5)
        self.set_text_color(50, 50, 70)

        y0 = self.get_y()
        bh = len(lines) * 5 + 4
        if y0 + bh > self.h - 16:
            self.add_page()
            y0 = self.get_y()

        rh = min(bh, 110)
        self.rect(self.l_margin, y0, self.w - self.l_margin - self.r_margin, rh, "F")
        self.set_xy(self.l_margin + 3, y0 + 2)

        for cl in lines:
            if self.get_y() > self.h - 18:
                break
            self.cell(0, 5, clean_emoji(cl), new_x="LMARGIN", new_y="NEXT")

        self.set_text_color(*TEXT_DARK)
        self.ln(3)


def parse_pages(md_text):
    parts = re.split(r"---\s*\n\s*<!--\s*PAGE\s+(\d+)\s*-->", md_text)
    pages = []
    i = 1
    while i < len(parts) - 1:
        pages.append((int(parts[i]), parts[i + 1].strip()))
        i += 2
    return pages


def extract_title(page_text):
    lines = page_text.split("\n")
    title = ""
    start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## ") and not s.startswith("### "):
            title = s[3:].strip()
            start = i + 1
            break
    return title, lines[start:]


def main():
    with open(INPUT_MD, "r", encoding="utf-8") as f:
        md_text = f.read()

    pages = parse_pages(md_text)
    pdf = BPReport()
    pdf.add_cover_page()

    # Merge: these continue on same page to avoid half-empty pages
    # Don't force merge too aggressively — allow natural flow
    merge_with_previous = {11}  # only merge conclusion with roadmap

    for pn, pt in pages:
        title, cl = extract_title(pt)
        if not title:
            for line in cl:
                if line.strip().startswith("#"):
                    title = line.strip().lstrip("#").strip()
                    break
            if not title:
                continue

        pdf.add_section_page(title, cl, force_new_page=pn not in merge_with_previous)

    pdf.output(OUTPUT_PDF)
    print(f"PDF generated: {OUTPUT_PDF}")
    print(f"Total pages: {pdf.page_no()}")


if __name__ == "__main__":
    main()
