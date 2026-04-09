"""
Generate a comprehensive PDF from all project manual markdown files.
Optimized for technical documentation with Chinese font support.
"""
import re
import os
import glob
from fpdf import FPDF

# ── Configuration ──────────────────────────────────────────────
FONT_PATH = "C:/Windows/Fonts/NotoSansSC-VF.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/simhei.ttf"
OUTPUT_PDF = "复旦管院智识库_项目手册.pdf"

FUDAN_BLUE = (13, 7, 131)
FUDAN_ORANGE = (234, 107, 0)
FUDAN_DARK = (10, 5, 96)
WHITE = (255, 255, 255)
LIGHT_GRAY = (245, 245, 250)
TEXT_DARK = (30, 30, 40)
TEXT_MED = (80, 80, 100)
CODE_BG = (240, 240, 245)


def clean_text(text):
    """Strip markdown formatting and emoji."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"&nbsp;", " ", text)
    # Remove common emoji
    for ch in ["\u2705", "\U0001f504", "\U0001f4cb", "\U0001f52e",
               "\u2714", "\u2718", "\u26a0", "\u2139"]:
        text = text.replace(ch, "")
    return text


class ManualPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("NotoSC", "", FONT_PATH)
        self.add_font("SimHei", "", FONT_BOLD_PATH)
        self.set_auto_page_break(auto=True, margin=16)
        self.current_chapter = ""

    def header(self):
        if self.page_no() > 1:
            self.set_font("NotoSC", "", 6.5)
            self.set_text_color(*TEXT_MED)
            self.cell(0, 4, "复旦管院智识库 — 项目手册", align="L")
            ch_display = self.current_chapter[:30] if self.current_chapter else ""
            self.cell(0, 4, ch_display, align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*FUDAN_BLUE)
            self.set_line_width(0.2)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("NotoSC", "", 6.5)
        self.set_text_color(*TEXT_MED)
        self.cell(0, 5, f"— {self.page_no()} —", align="C")

    def add_cover(self):
        self.add_page()
        self.set_fill_color(*FUDAN_DARK)
        self.rect(0, 0, 210, 297, "F")

        self.set_fill_color(*FUDAN_ORANGE)
        self.rect(20, 75, 50, 2.5, "F")

        self.set_y(84)
        self.set_font("SimHei", "", 32)
        self.set_text_color(*WHITE)
        self.cell(0, 16, "复旦管院智识库", align="L", new_x="LMARGIN", new_y="NEXT")

        self.set_font("NotoSC", "", 16)
        self.set_text_color(200, 200, 220)
        self.cell(0, 10, "项目技术手册", align="L", new_x="LMARGIN", new_y="NEXT")

        self.ln(6)
        self.set_font("NotoSC", "", 10)
        self.set_text_color(170, 170, 190)
        desc_lines = [
            "原子级技术文档 · 覆盖全部架构与实现细节",
            "共 15 章 · 涵盖后端/前端/AI/数据库/API 全栈",
        ]
        for line in desc_lines:
            self.cell(0, 7, line, align="L", new_x="LMARGIN", new_y="NEXT")

        # TOC preview
        self.ln(10)
        self.set_draw_color(80, 80, 120)
        self.set_line_width(0.15)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(5)

        self.set_font("NotoSC", "", 8.5)
        self.set_text_color(160, 160, 180)
        chapters = [
            "01 项目概述", "02 技术架构", "03 后端架构", "04 数据库设计",
            "05 RAG搜索引擎", "06 AI服务体系", "07 AI对话系统",
            "08 会员与权限体系", "09 编辑后台CMS", "10 前端架构",
            "11 前端页面与交互", "12 数据管道", "13 国际化与翻译", "14 API接口文档",
        ]
        for i in range(0, len(chapters), 2):
            left = chapters[i] if i < len(chapters) else ""
            right = chapters[i+1] if i+1 < len(chapters) else ""
            self.cell(85, 6, left, align="L")
            self.cell(85, 6, right, align="L", new_x="LMARGIN", new_y="NEXT")

        # Bottom info
        self.set_y(250)
        self.set_draw_color(80, 80, 120)
        self.line(20, 250, 190, 250)
        self.ln(5)
        self.set_font("NotoSC", "", 10)
        self.set_text_color(170, 170, 190)
        self.cell(0, 8, "KDCC 团队 · 2026 年 4 月", align="L", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "版本 v1.0", align="L", new_x="LMARGIN", new_y="NEXT")

    def add_chapter(self, title, lines):
        """Start new chapter on a new page."""
        self.current_chapter = title
        self.add_page()
        self.set_text_color(*TEXT_DARK)

        # Chapter title bar
        self.set_fill_color(*FUDAN_ORANGE)
        self.rect(self.l_margin, self.get_y(), 35, 2, "F")
        self.ln(4)
        self.set_font("SimHei", "", 16)
        self.set_text_color(*FUDAN_DARK)
        self.cell(0, 10, clean_text(title), align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        self._render_lines(lines)

    def _render_lines(self, lines):
        i = 0
        in_code = False
        code_lines = []
        in_table = False
        table_rows = []

        while i < len(lines):
            line = lines[i]

            # Code block toggle
            if line.strip().startswith("```"):
                if in_code:
                    self._render_code(code_lines)
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

            # Table
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
                    self._render_table(table_rows)
                    in_table = False
                    table_rows = []
                i += 1
                continue

            s = line.strip()

            # Skip blanks / html
            if not s or s in ["<br>", "<br><br>", "---"]:
                self.ln(1)
                i += 1
                continue
            if s.startswith("<") or s.startswith("<!--"):
                i += 1
                continue

            # H1 (chapter title already rendered, skip duplicates)
            if s.startswith("# ") and not s.startswith("## "):
                i += 1
                continue

            # H2
            if s.startswith("## "):
                text = clean_text(s[3:])
                self.ln(3)
                self.set_font("SimHei", "", 13)
                self.set_text_color(*FUDAN_BLUE)
                # Blue left bar
                y = self.get_y()
                self.set_fill_color(*FUDAN_BLUE)
                self.rect(self.l_margin, y, 1.5, 7, "F")
                self.set_x(self.l_margin + 4)
                self.multi_cell(self.w - self.l_margin - self.r_margin - 4, 7,
                                text, new_x="LMARGIN", new_y="NEXT")
                self.set_text_color(*TEXT_DARK)
                self.ln(1.5)
                i += 1
                continue

            # H3
            if s.startswith("### "):
                text = clean_text(s[4:])
                self.ln(2)
                self.set_font("SimHei", "", 10.5)
                self.set_text_color(*FUDAN_DARK)
                self.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")
                self.set_text_color(*TEXT_DARK)
                self.ln(1)
                i += 1
                continue

            # H4
            if s.startswith("#### "):
                text = clean_text(s[5:])
                self.ln(1.5)
                self.set_font("SimHei", "", 9)
                self.set_text_color(60, 60, 90)
                self.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
                self.set_text_color(*TEXT_DARK)
                self.ln(0.5)
                i += 1
                continue

            # Blockquote (collect consecutive lines)
            if s.startswith("> ") or s == ">":
                parts = []
                while i < len(lines):
                    ls = lines[i].strip()
                    if ls.startswith("> "):
                        parts.append(clean_text(ls[2:]))
                        i += 1
                    elif ls == ">":
                        parts.append("")
                        i += 1
                    else:
                        break
                qt = " ".join(p for p in parts if p)
                if qt:
                    y = self.get_y()
                    self.set_fill_color(*FUDAN_ORANGE)
                    self.rect(self.l_margin, y, 1.2, 6, "F")
                    self.set_x(self.l_margin + 3.5)
                    self.set_font("NotoSC", "", 7.5)
                    self.set_text_color(*TEXT_MED)
                    self.multi_cell(self.w - self.l_margin - self.r_margin - 3.5, 4.5,
                                    qt, new_x="LMARGIN", new_y="NEXT")
                    self.set_text_color(*TEXT_DARK)
                    self.ln(1)
                continue

            # Bullet (numbered or dash)
            bullet_match = re.match(r"^(\d+)\.\s+(.+)", s)
            if s.startswith("- ") or s.startswith("* ") or bullet_match:
                if bullet_match:
                    marker = f"{bullet_match.group(1)}."
                    text = clean_text(bullet_match.group(2))
                else:
                    marker = "·"
                    text = clean_text(s[2:])
                self.set_font("NotoSC", "", 7.5)
                self.cell(5, 4, marker)
                self.multi_cell(self.w - self.l_margin - self.r_margin - 5, 4,
                                text, new_x="LMARGIN", new_y="NEXT")
                self.ln(0.3)
                i += 1
                continue

            # Bold standalone line
            if s.startswith("**") and s.endswith("**"):
                text = clean_text(s)
                self.set_font("SimHei", "", 8)
                self.multi_cell(0, 4.5, text, new_x="LMARGIN", new_y="NEXT")
                self.set_font("NotoSC", "", 7.5)
                self.ln(0.3)
                i += 1
                continue

            # Regular paragraph
            text = clean_text(s)
            self.set_font("NotoSC", "", 7.5)
            self.multi_cell(0, 4, text, new_x="LMARGIN", new_y="NEXT")
            self.ln(0.3)
            i += 1

    def _render_table(self, rows):
        if not rows:
            return
        num_cols = max(len(r) for r in rows)
        if num_cols == 0:
            return

        usable_w = self.w - self.l_margin - self.r_margin

        # Column widths from content
        col_lens = []
        for ci in range(num_cols):
            mx = 0
            for r in rows:
                if ci < len(r):
                    mx = max(mx, len(clean_text(r[ci])))
            col_lens.append(max(mx, 2))
        total = sum(col_lens)
        col_w = [max(10, l / total * usable_w) for l in col_lens]
        total = sum(col_w)
        col_w = [w / total * usable_w for w in col_w]

        for ri, row in enumerate(rows):
            is_header = (ri == 0)
            if is_header:
                self.set_fill_color(*FUDAN_DARK)
                self.set_text_color(*WHITE)
                self.set_font("SimHei", "", 6.5)
            else:
                self.set_fill_color(*(LIGHT_GRAY if ri % 2 == 0 else WHITE))
                self.set_text_color(*TEXT_DARK)
                self.set_font("NotoSC", "", 6.5)

            cell_texts = []
            max_lines = 1
            for ci in range(num_cols):
                text = clean_text(row[ci] if ci < len(row) else "")
                cell_texts.append(text)
                cpl = max(1, int(col_w[ci] / 2))
                nl = max(1, (len(text) + cpl - 1) // cpl)
                max_lines = max(max_lines, nl)

            row_h = max(4.5, max_lines * 3.8 + 0.5)
            row_h = min(row_h, 22)

            if self.get_y() + row_h > self.h - 16:
                self.add_page()

            x0, y0 = self.get_x(), self.get_y()
            for ci in range(num_cols):
                self.set_xy(x0 + sum(col_w[:ci]), y0)
                self.multi_cell(col_w[ci], 3.8, cell_texts[ci],
                                border=0, fill=True,
                                new_x="RIGHT", new_y="TOP", align="L")
            self.set_xy(x0, y0 + row_h)

        self.set_text_color(*TEXT_DARK)
        self.ln(1.5)

    def _render_code(self, lines):
        self.set_fill_color(*CODE_BG)
        self.set_font("NotoSC", "", 6)
        self.set_text_color(50, 50, 70)

        y0 = self.get_y()
        block_h = len(lines) * 3.2 + 3
        if y0 + block_h > self.h - 16:
            self.add_page()
            y0 = self.get_y()

        render_h = min(block_h, 90)
        self.rect(self.l_margin, y0, self.w - self.l_margin - self.r_margin, render_h, "F")
        self.set_xy(self.l_margin + 2, y0 + 1.5)

        max_code_lines = 25  # Truncate very long code blocks
        for idx, cl in enumerate(lines[:max_code_lines]):
            if self.get_y() > self.h - 18:
                break
            self.cell(0, 3.2, clean_text(cl), new_x="LMARGIN", new_y="NEXT")

        if len(lines) > max_code_lines:
            self.set_font("NotoSC", "", 5.5)
            self.set_text_color(*TEXT_MED)
            self.cell(0, 3.2, f"  ... (共 {len(lines)} 行，已截断显示)", new_x="LMARGIN", new_y="NEXT")

        self.set_text_color(*TEXT_DARK)
        self.ln(2)


def main():
    # Collect all chapter files in order
    manual_dir = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(manual_dir, "*.md")))

    # Filter to numbered chapters (01-14), skip 00-目录
    chapter_files = []
    for f in files:
        basename = os.path.basename(f)
        if re.match(r"^\d{2}-", basename) and basename != "00-目录.md":
            chapter_files.append(f)

    print(f"Found {len(chapter_files)} chapters to process")

    pdf = ManualPDF()
    pdf.add_cover()

    for filepath in chapter_files:
        basename = os.path.basename(filepath)
        print(f"  Processing: {basename}")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")

        # Extract title from first H1
        title = basename.replace(".md", "")
        for line in lines:
            if line.strip().startswith("# ") and not line.strip().startswith("## "):
                title = line.strip()[2:].strip()
                break

        pdf.add_chapter(title, lines)

    output_path = os.path.join(manual_dir, OUTPUT_PDF)
    pdf.output(output_path)
    print(f"\nPDF generated: {output_path}")
    print(f"Total pages: {pdf.page_no()}")


if __name__ == "__main__":
    main()
