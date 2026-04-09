from __future__ import annotations

import re
from html import escape


SUMMARY_PREVIEW_MARKER = 'data-summary-preview="true"'


def is_summary_preview_html(value: str | None) -> bool:
    html = str(value or "").strip()
    return "summary-preview-shell" in html and SUMMARY_PREVIEW_MARKER in html


def _escape_html(value: str) -> str:
    return escape(str(value or ""), quote=True)


def _render_inline_markdown(value: str) -> str:
    html = _escape_html(value)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<em>\1</em>", html)
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    return html


def _render_markdown_blocks(markdown: str) -> str:
    lines = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[dict[str, object]] = []
    paragraph: list[str] = []
    current_list: dict[str, object] | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        blocks.append({"type": "paragraph", "text": " ".join(paragraph).strip()})
        paragraph = []

    def flush_list() -> None:
        nonlocal current_list
        if not current_list or not current_list.get("items"):
            current_list = None
            return
        blocks.append(current_list)
        current_list = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue

        if re.fullmatch(r"-{3,}", line):
            flush_paragraph()
            flush_list()
            blocks.append({"type": "hr"})
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading.group(1)),
                    "text": heading.group(2).strip(),
                }
            )
            continue

        bullet = re.match(r"^[-*+]\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            if not current_list or current_list.get("type") != "ul":
                flush_list()
                current_list = {"type": "ul", "items": []}
            current_list["items"].append(bullet.group(1).strip())
            continue

        ordered = re.match(r"^\d+\.\s+(.+)$", line)
        if ordered:
            flush_paragraph()
            if not current_list or current_list.get("type") != "ol":
                flush_list()
                current_list = {"type": "ol", "items": []}
            current_list["items"].append(ordered.group(1).strip())
            continue

        strong_only = re.match(r"^\*\*(.+?)\*\*$", line)
        if strong_only:
            flush_paragraph()
            flush_list()
            blocks.append({"type": "label", "text": strong_only.group(1).strip()})
            continue

        paragraph.append(line)

    flush_paragraph()
    flush_list()

    rendered: list[str] = []
    for block in blocks:
        block_type = str(block["type"])
        if block_type == "heading":
            level = int(block["level"])
            safe_text = _render_inline_markdown(str(block["text"]))
            if level <= 2:
                rendered.append(
                    '<h2 style="margin: 34px 0 18px; text-align: center; color: #4E8FEA; '
                    'font-family: Georgia, \'Times New Roman\', \'PingFang SC\', serif; '
                    'font-size: 22px; line-height: 1.45; font-weight: 800;">'
                    f"{safe_text}</h2>"
                )
                continue
            rendered.append(
                '<h3 style="margin: 28px 0 14px; color: #1F3251; '
                'font-family: Georgia, \'Times New Roman\', \'PingFang SC\', serif; '
                'font-size: 18px; line-height: 1.5; font-weight: 700;">'
                f"{safe_text}</h3>"
            )
            continue

        if block_type == "label":
            rendered.append(
                '<p style="margin: 0 0 18px; color: #1F3251; font-size: 15px; '
                'line-height: 1.85; font-weight: 700;">'
                f"{_render_inline_markdown(str(block['text']))}</p>"
            )
            continue

        if block_type == "hr":
            rendered.append('<p style="margin: 18px 0 24px; border-top: 1px solid #D9E4F2; height: 0;"></p>')
            continue

        if block_type in {"ul", "ol"}:
            tag = block_type
            items = "".join(
                '<li style="margin: 0 0 10px; color: #475569; font-size: 15px; line-height: 1.88;">'
                f"{_render_inline_markdown(str(item))}</li>"
                for item in block.get("items", [])
            )
            rendered.append(f'<{tag} style="margin: 0 0 26px; padding-left: 24px;">{items}</{tag}>')
            continue

        rendered.append(
            '<p style="margin: 0 0 28px; color: #475569; font-size: 15px; '
            'line-height: 1.92; letter-spacing: 0.01em;">'
            f"{_render_inline_markdown(str(block['text']))}</p>"
        )

    return "".join(rendered)


def render_summary_preview_html(summary: str, *, language: str = "zh") -> str | None:
    text = str(summary or "").strip()
    if not text:
        return None

    body_html = _render_markdown_blocks(text)
    if not body_html:
        return None

    html_lang = "en" if str(language or "").strip().lower().startswith("en") else "zh-CN"
    return f"""<!doctype html>
<html lang="{html_lang}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; padding: 12px 8px 20px; background: #F8FBFF; font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }}
      .summary-preview-shell {{ max-width: 760px; margin: 0 auto; background: #FFFFFF; }}
      .summary-preview-article {{ padding: 18px 18px 12px; background: #FFFFFF; }}
      .summary-preview-inner {{ margin: 0 auto; width: 100%; max-width: 700px; }}
      .summary-preview-dots {{ margin: 0 0 16px 4px; line-height: 0; }}
      .summary-preview-dot {{ display: inline-block; width: 8px; height: 8px; margin-right: 28px; border-radius: 999px; background: #CBD5E1; }}
      strong {{ padding: 0 6px 1px; border-bottom: 1px solid #D3E6FB; background: #EAF3FF; color: #243B5A; font-weight: 700; }}
      code {{ padding: 0 5px; border-radius: 6px; background: #EFF3F8; color: #334155; font-size: 0.94em; }}
      em {{ color: #334155; }}
    </style>
  </head>
  <body>
    <div class="summary-preview-shell" {SUMMARY_PREVIEW_MARKER}>
      <section class="summary-preview-article">
        <article class="summary-preview-inner">
          <p class="summary-preview-dots"><span class="summary-preview-dot"></span><span class="summary-preview-dot"></span><span class="summary-preview-dot" style="margin-right:0;"></span></p>
          {body_html}
        </article>
      </section>
    </div>
  </body>
</html>"""
