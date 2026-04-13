from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import get_connection
from backend.services.article_visibility_service import is_hidden_low_value_article

FRONTEND_DIR = PROJECT_ROOT / "frontend"
REPORTS_DIR = PROJECT_ROOT / "reports"
TODO_DIR = PROJECT_ROOT / "todo"
SCREENSHOT_DIR = PROJECT_ROOT / "qa" / "screenshots" / "round65_articles"
SUPERVISOR_LOG = REPORTS_DIR / "round65_supervisor.log"
CHECK_INTERVAL_SECONDS = 30


def append_log(message: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")


def round65_todo_path() -> Path:
    candidates = sorted(TODO_DIR.glob("round65_*.md"))
    if not candidates:
        raise FileNotFoundError("round65 todo file not found")
    return candidates[0]


def round66_todo_path() -> Path:
    return TODO_DIR / "round66_自动补跑与验收续轮.md"


def progress_snapshot() -> dict[str, int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, content
            FROM articles
            WHERE source != 'editorial'
            """
        ).fetchall()
        visible_count = sum(1 for row in rows if not is_hidden_low_value_article(row))
        full_round_count = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id)
            FROM article_ai_outputs
            WHERE worker_name LIKE 'round65-full-%'
            """
        ).fetchone()[0]
    return {
        "visible_articles": int(visible_count),
        "full_round_distinct": int(full_round_count or 0),
    }


def update_round65_todo(*, full_complete: bool = False, screenshot_complete: bool = False) -> None:
    path = round65_todo_path()
    text = path.read_text(encoding="utf-8")
    replacements = {}
    if full_complete:
        replacements["- [ ] 对 1700 篇可见文章持续执行 round65 beauty 全量回填"] = "- [x] 对 1700 篇可见文章持续执行 round65 beauty 全量回填"
        replacements["- [ ] 收口门槛一：1700 篇可见文章全部完成 round65 全量回填"] = "- [x] 收口门槛一：1700 篇可见文章全部完成 round65 全量回填"
    if screenshot_complete:
        replacements["- [ ] 全量回填完成后重新抽检 10 篇中英文 20 图"] = "- [x] 全量回填完成后重新抽检 10 篇中英文 20 图"
        replacements["- [ ] 收口门槛二：重新执行 10 篇中英文 20 图截图验收"] = "- [x] 收口门槛二：重新执行 10 篇中英文 20 图截图验收"
    for source, target in replacements.items():
        text = text.replace(source, target)
    path.write_text(text, encoding="utf-8")


def write_round66(reason: str) -> None:
    path = round66_todo_path()
    body = (
        "# Round 66：自动补跑与验收续轮\n\n"
        "## P0 问题来源\n"
        f"- [x] Round65 自动闭环判定未通过：{reason}\n\n"
        "## P0 继续推进\n"
        "- [ ] 重新定位未达标链路\n"
        "- [ ] 补跑受影响文章\n"
        "- [ ] 重新执行 10 篇中英文 20 图截图验收\n"
        "- [ ] 达到要求后再收口\n"
    )
    path.write_text(body, encoding="utf-8")
    append_log(f"round66 todo created | reason={reason}")


def main_screenshot_count() -> int:
    if not SCREENSHOT_DIR.exists():
        return 0
    count = 0
    for item in SCREENSHOT_DIR.glob("*.png"):
        stem = item.stem
        if not stem.startswith(("zh-article-", "en-article-")):
            continue
        if stem.endswith("-body") or stem.endswith("-latest"):
            continue
        count += 1
    return count


def create_contact_sheet() -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # noqa: BLE001
        append_log(f"contact sheet skipped | pillow unavailable: {exc}")
        return

    files = sorted(
        [
            path
            for path in SCREENSHOT_DIR.glob("*.png")
            if path.stem.startswith(("zh-article-", "en-article-"))
            and not path.stem.endswith("-body")
            and not path.stem.endswith("-latest")
        ]
    )
    if not files:
        return
    thumb_w, thumb_h = 320, 356
    cols = 4
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 28)), "#f4f2ec")
    for idx, file in enumerate(files):
        image = Image.open(file).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        card = Image.new("RGB", (thumb_w, thumb_h), "white")
        offset = ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2)
        card.paste(image, offset)
        x = (idx % cols) * thumb_w
        y = (idx // cols) * (thumb_h + 28)
        sheet.paste(card, (x, y))
        draw = ImageDraw.Draw(sheet)
        draw.text((x + 8, y + thumb_h + 6), file.stem, fill="#334155")
    sheet.save(SCREENSHOT_DIR / "contact-sheet.png")
    append_log("contact sheet refreshed")


def run_acceptance_cycle() -> tuple[bool, str]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["node", "scripts/article_round65_acceptance.mjs"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        reason = (completed.stderr or completed.stdout or "unknown acceptance error").strip()
        append_log(f"acceptance failed | {reason[:600]}")
        return False, reason[:600]
    count = main_screenshot_count()
    create_contact_sheet()
    if count != 20:
        reason = f"expected 20 main screenshots, got {count}"
        append_log(f"acceptance incomplete | {reason}")
        return False, reason
    append_log("acceptance completed | 20 screenshots generated")
    return True, "ok"


def main() -> int:
    append_log("supervisor started")
    acceptance_done = False
    while True:
        snapshot = progress_snapshot()
        full_complete = snapshot["full_round_distinct"] >= snapshot["visible_articles"] and snapshot["visible_articles"] > 0
        if full_complete:
            update_round65_todo(full_complete=True)
            if not acceptance_done:
                append_log("full round complete | triggering acceptance cycle")
                ok, reason = run_acceptance_cycle()
                if ok:
                    update_round65_todo(screenshot_complete=True)
                    acceptance_done = True
                    append_log("round65 supervisor completed mechanical acceptance")
                else:
                    write_round66(reason)
                    break
        time.sleep(CHECK_INTERVAL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
