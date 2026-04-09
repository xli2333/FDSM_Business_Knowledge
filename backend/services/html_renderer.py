from __future__ import annotations

import re
from html import escape


def strip_markdown(content: str) -> str:
    text = content.replace("\r\n", "\n")
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.M)
    text = re.sub(r"[*_~#>-]", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _format_inline(text: str) -> str:
    formatted = escape(text)
    formatted = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2" target="_blank" rel="noreferrer">\1</a>',
        formatted,
    )
    formatted = re.sub(r"`([^`]+)`", r"<code>\1</code>", formatted)
    formatted = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", formatted)
    formatted = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", formatted)
    return formatted


def markdown_to_html(content: str) -> str:
    lines = content.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    index = 0

    def parse_list(start_index: int, ordered: bool) -> tuple[str, int]:
        items: list[str] = []
        cursor = start_index
        pattern = r"^\s*\d+\.\s+(.*)$" if ordered else r"^\s*[-*+]\s+(.*)$"
        while cursor < len(lines):
            match = re.match(pattern, lines[cursor].rstrip())
            if not match:
                break
            items.append(f"<li>{_format_inline(match.group(1).strip())}</li>")
            cursor += 1
        tag = "ol" if ordered else "ul"
        return f"<{tag}>{''.join(items)}</{tag}>", cursor

    while index < len(lines):
        raw_line = lines[index].rstrip()
        line = raw_line.strip()
        if not line:
            index += 1
            continue

        if line.startswith("```"):
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
            blocks.append(f"<h{level}>{_format_inline(heading_match.group(2).strip())}</h{level}>")
            index += 1
            continue

        if re.match(r"^\s*[-*+]\s+", raw_line):
            block, index = parse_list(index, ordered=False)
            blocks.append(block)
            continue

        if re.match(r"^\s*\d+\.\s+", raw_line):
            block, index = parse_list(index, ordered=True)
            blocks.append(block)
            continue

        if line.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].strip())
                index += 1
            blocks.append(
                "<blockquote>{}</blockquote>".format(
                    "".join(f"<p>{_format_inline(item)}</p>" for item in quote_lines if item)
                )
            )
            continue

        if re.fullmatch(r"[-*_]{3,}", line):
            blocks.append("<hr />")
            index += 1
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if not next_line:
                index += 1
                break
            if (
                next_line.startswith("#")
                or next_line.startswith(">")
                or next_line.startswith("```")
                or re.match(r"^\s*[-*+]\s+", lines[index])
                or re.match(r"^\s*\d+\.\s+", lines[index])
                or re.fullmatch(r"[-*_]{3,}", next_line)
            ):
                break
            paragraph_lines.append(next_line)
            index += 1
        blocks.append(f"<p>{_format_inline(' '.join(paragraph_lines))}</p>")

    return "\n".join(blocks)


def _tag_chip_html(tags: list[dict]) -> str:
    chips = []
    for tag in tags[:8]:
        color = tag.get("color") or "#64748b"
        name = escape(tag.get("name") or "")
        chips.append(
            f'<span class="tag-chip" style="--tag-color:{color};">{name}</span>'
        )
    return "".join(chips)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text or ""))


def render_editorial_package(article: dict, tags: list[dict], *, language: str = "zh-CN") -> dict[str, str]:
    is_english = str(language or "").strip().lower().startswith("en")
    body_html = markdown_to_html(article.get("content_markdown") or "")
    summary = article.get("excerpt") or strip_markdown(article.get("content_markdown") or "")[:120]
    summary = summary.strip() or ("Summary unavailable" if is_english else "暂无摘要")
    title = escape(article.get("title") or "")
    subtitle_raw = str(article.get("subtitle") or "").strip()
    if is_english and _contains_cjk(subtitle_raw):
        subtitle_raw = ""
    subtitle = escape(subtitle_raw)
    author = escape(article.get("author") or ("Editorial Desk" if is_english else "编辑部"))
    organization = escape(article.get("organization") or ("Fudan Business Knowledge" if is_english else "复旦商业知识库"))
    publish_date = escape(article.get("publish_date") or "")
    source_url = article.get("source_url") or ""
    source_link_label = "View source article" if is_english else "查看原始来源"
    source_link = (
        f'<a href="{escape(source_url)}" target="_blank" rel="noreferrer">{source_link_label}</a>'
        if source_url
        else ""
    )
    visible_tags = tags
    if is_english:
        visible_tags = [tag for tag in tags if not _contains_cjk(str(tag.get("name") or ""))]
    chips_html = _tag_chip_html(visible_tags)
    wechat_tags_html = "".join(
        f'<span class="wechat-tag">{escape(tag.get("name") or "")}</span>' for tag in visible_tags[:6]
    )
    html_lang = "en" if is_english else "zh-CN"
    body_font = (
        '"Aptos", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
        if is_english
        else '"Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    )
    title_font = (
        '"Iowan Old Style", "Palatino Linotype", Georgia, serif'
        if is_english
        else '"Noto Serif SC", "Songti SC", serif'
    )
    article_leading = "1.82" if is_english else "2"
    summary_leading = "1.78" if is_english else "1.9"
    web_template_label = "Template: Web editorial layout" if is_english else "生成模板：Web Editorial Template"
    wechat_template_label = "Template: WeChat long-form layout" if is_english else "模板：微信公众号长文排版"

    web_html = f"""<!doctype html>
<html lang="{html_lang}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      :root {{
        --fudan-blue: #0d0783;
        --fudan-orange: #ea6b00;
        --paper: #fcfbf8;
        --ink: #162033;
        --muted: #5b6477;
        --line: rgba(15, 23, 42, 0.12);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: {body_font};
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(13, 7, 131, 0.08), transparent 30%),
          linear-gradient(180deg, #fcfbf8 0%, #f5f2ea 100%);
      }}
      .shell {{ max-width: 940px; margin: 0 auto; padding: 40px 20px 72px; }}
      .hero {{
        background: linear-gradient(145deg, rgba(13,7,131,0.98), rgba(10,5,96,0.86) 58%, rgba(234,107,0,0.36));
        color: #fff;
        border-radius: 32px;
        padding: 36px;
        box-shadow: 0 28px 80px rgba(13, 7, 131, 0.16);
      }}
      .eyebrow {{
        display: inline-block;
        margin-bottom: 18px;
        letter-spacing: 0.28em;
        text-transform: uppercase;
        font-size: 12px;
        color: rgba(255,255,255,0.72);
      }}
      h1 {{
        margin: 0;
        font-family: {title_font};
        font-size: {48 if is_english else 52}px;
        line-height: 1.12;
      }}
      .subtitle {{ margin-top: 14px; font-size: 20px; color: rgba(255,255,255,0.86); }}
      .meta {{ margin-top: 24px; display: flex; flex-wrap: wrap; gap: 12px 20px; font-size: 14px; color: rgba(255,255,255,0.78); }}
      .summary {{
        margin-top: 24px;
        padding: 18px 20px;
        border-radius: 24px;
        background: rgba(255,255,255,0.12);
        font-size: 15px;
        line-height: {summary_leading};
      }}
      .chip-row {{ margin-top: 20px; display: flex; flex-wrap: wrap; gap: 10px; }}
      .tag-chip {{
        display: inline-flex;
        align-items: center;
        padding: 8px 12px;
        border-radius: 999px;
        border: 1px solid color-mix(in srgb, var(--tag-color) 28%, white);
        background: color-mix(in srgb, var(--tag-color) 10%, white);
        color: color-mix(in srgb, var(--tag-color) 74%, black);
        font-size: 12px;
        font-weight: 700;
      }}
      .article {{
        margin-top: 28px;
        border-radius: 32px;
        background: rgba(255,255,255,0.94);
        border: 1px solid var(--line);
        padding: 38px 40px;
        box-shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
      }}
      .article h1, .article h2, .article h3, .article h4 {{
        font-family: {title_font};
        color: var(--fudan-blue);
      }}
      .article h2 {{ margin: 34px 0 16px; font-size: 28px; }}
      .article h3 {{ margin: 28px 0 12px; font-size: 22px; }}
      .article p, .article li {{
        font-size: {17 if is_english else 16}px;
        line-height: {article_leading};
        color: var(--ink);
      }}
      .article blockquote {{
        margin: 24px 0;
        padding: 4px 0 4px 18px;
        border-left: 4px solid var(--fudan-orange);
        color: var(--muted);
      }}
      .article code {{
        border-radius: 8px;
        padding: 2px 6px;
        background: rgba(13, 7, 131, 0.08);
        color: var(--fudan-blue);
      }}
      .article pre {{
        overflow-x: auto;
        padding: 18px;
        border-radius: 18px;
        background: #0f172a;
        color: #f8fafc;
      }}
      .article a {{ color: var(--fudan-orange); text-decoration: none; }}
      .footer {{
        margin-top: 24px;
        display: flex;
        justify-content: space-between;
        gap: 20px;
        padding-top: 20px;
        border-top: 1px dashed var(--line);
        color: var(--muted);
        font-size: 14px;
      }}
      @media (max-width: 768px) {{
        .shell {{ padding: 20px 14px 40px; }}
        .hero, .article {{ padding: 24px 20px; border-radius: 24px; }}
        h1 {{ font-size: 34px; }}
      }}
    </style>
  </head>
  <body>
    <div class="shell">
      <section class="hero">
        <div class="eyebrow">Fudan Business Knowledge</div>
        <h1>{title}</h1>
        {f'<div class="subtitle">{subtitle}</div>' if subtitle else ''}
        <div class="meta">
          <span>{author}</span>
          <span>{organization}</span>
          <span>{publish_date}</span>
        </div>
        <div class="summary">{escape(summary)}</div>
        {f'<div class="chip-row">{chips_html}</div>' if chips_html else ''}
      </section>

      <article class="article">
        {body_html}
        <div class="footer">
          <span>{web_template_label}</span>
          <span>{source_link}</span>
        </div>
      </article>
    </div>
  </body>
</html>"""

    wechat_html = f"""<!doctype html>
<html lang="{html_lang}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        padding: 0;
        background: #eef2f7;
        font-family: {body_font};
        color: #1f2937;
      }}
      .wechat-shell {{
        max-width: 760px;
        margin: 0 auto;
        padding: 20px 12px 32px;
      }}
      .wechat-card {{
        background: #ffffff;
        border-radius: 28px;
        overflow: hidden;
        box-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
      }}
      .wechat-head {{
        padding: 32px 26px 28px;
        background:
          radial-gradient(circle at top right, rgba(234,107,0,0.24), transparent 36%),
          linear-gradient(180deg, rgba(13,7,131,0.98), rgba(10,5,96,0.94));
        color: #fff;
      }}
      .wechat-brand {{
        margin-bottom: 16px;
        font-size: 12px;
        letter-spacing: 0.3em;
        text-transform: uppercase;
        color: rgba(255,255,255,0.72);
      }}
      .wechat-title {{
        margin: 0;
        font-family: {title_font};
        font-size: {32 if is_english else 34}px;
        line-height: 1.28;
      }}
      .wechat-subtitle {{
        margin-top: 12px;
        font-size: 17px;
        line-height: {summary_leading};
        color: rgba(255,255,255,0.84);
      }}
      .wechat-meta {{
        margin-top: 20px;
        padding-top: 16px;
        border-top: 1px solid rgba(255,255,255,0.18);
        font-size: 13px;
        line-height: 1.8;
        color: rgba(255,255,255,0.76);
      }}
      .wechat-summary {{
        margin-top: 20px;
        padding: 16px 18px;
        border-radius: 20px;
        background: rgba(255,255,255,0.12);
        font-size: 15px;
        line-height: {summary_leading};
      }}
      .wechat-tags {{ margin-top: 18px; display: flex; flex-wrap: wrap; gap: 8px; }}
      .wechat-tag {{
        display: inline-flex;
        align-items: center;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.18);
        font-size: 12px;
        color: #fff;
      }}
      .wechat-body {{
        padding: 28px 26px 32px;
      }}
      .wechat-body h1, .wechat-body h2, .wechat-body h3, .wechat-body h4 {{
        font-family: {title_font};
        color: #0d0783;
      }}
      .wechat-body h2 {{
        margin: 30px 0 14px;
        padding-left: 12px;
        border-left: 4px solid #ea6b00;
        font-size: 24px;
        line-height: 1.5;
      }}
      .wechat-body h3 {{ margin: 24px 0 12px; font-size: 20px; }}
      .wechat-body p, .wechat-body li {{
        margin: 0 0 16px;
        font-size: {17 if is_english else 16}px;
        line-height: {article_leading};
        color: #334155;
      }}
      .wechat-body blockquote {{
        margin: 22px 0;
        padding: 14px 16px;
        border-radius: 18px;
        background: #f8fafc;
        color: #475569;
      }}
      .wechat-body code {{
        padding: 2px 6px;
        border-radius: 6px;
        background: rgba(13,7,131,0.08);
        color: #0d0783;
      }}
      .wechat-body pre {{
        overflow-x: auto;
        padding: 16px;
        border-radius: 18px;
        background: #0f172a;
        color: #f8fafc;
      }}
      .wechat-foot {{
        margin-top: 24px;
        padding-top: 18px;
        border-top: 1px dashed rgba(15, 23, 42, 0.14);
        font-size: 13px;
        line-height: 1.8;
        color: #64748b;
      }}
      .wechat-foot a {{
        color: #ea6b00;
        text-decoration: none;
      }}
    </style>
  </head>
  <body>
    <div class="wechat-shell">
      <article class="wechat-card">
        <section class="wechat-head">
          <div class="wechat-brand">Fudan Business Knowledge</div>
          <h1 class="wechat-title">{title}</h1>
          {f'<div class="wechat-subtitle">{subtitle}</div>' if subtitle else ''}
          <div class="wechat-meta">{author} · {organization} · {publish_date}</div>
          <div class="wechat-summary">{escape(summary)}</div>
          {f'<div class="wechat-tags">{wechat_tags_html}</div>' if wechat_tags_html else ''}
        </section>
        <section class="wechat-body">
          {body_html}
          <div class="wechat-foot">
            <div>{wechat_template_label}</div>
            {f'<div>{source_link}</div>' if source_link else ''}
          </div>
        </section>
      </article>
    </div>
  </body>
</html>"""

    return {
        "summary": summary,
        "html_web": web_html,
        "html_wechat": wechat_html,
    }
