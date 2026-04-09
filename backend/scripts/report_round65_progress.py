from __future__ import annotations

from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import get_connection
from backend.services.article_visibility_service import is_hidden_low_value_article


def main() -> int:
    screenshot_dir = PROJECT_ROOT / "qa" / "screenshots" / "round65_articles"
    screenshots = sorted(p for p in screenshot_dir.glob("*.png") if p.is_file())
    main_screenshots = [
        p
        for p in screenshots
        if p.name.startswith(("zh-article-", "en-article-")) and not p.stem.endswith("-body") and not p.stem.endswith("-latest")
    ]
    extra_screenshots = [p for p in screenshots if p not in main_screenshots]
    latest_shot = screenshots[-1].stat().st_mtime if screenshots else None

    with get_connection() as connection:
        article_rows = connection.execute(
            """
            SELECT id, title, content
            FROM articles
            WHERE source != 'editorial'
            """
        ).fetchall()
        visible_articles = [row for row in article_rows if not is_hidden_low_value_article(row)]
        visible_ids = {row["id"] for row in visible_articles}

        beauty_rows = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id)
            FROM article_ai_outputs
            WHERE format_model = 'fudan-wechat-preview-bridge-beauty'
            """
        ).fetchone()[0]

        full_rows = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id)
            FROM article_ai_outputs
            WHERE worker_name LIKE 'round65-full-%'
            """
        ).fetchone()[0]

        shard_rows = connection.execute(
            """
            SELECT worker_name, COUNT(DISTINCT article_id) AS count_articles, MAX(updated_at) AS updated_at
            FROM article_ai_outputs
            WHERE worker_name LIKE 'round65-full-%'
            GROUP BY worker_name
            ORDER BY worker_name
            """
        ).fetchall()

    print(f"timestamp: {datetime.now().isoformat(timespec='seconds')}")
    print(f"visible_articles: {len(visible_ids)}")
    print(f"beauty_rendered_distinct: {beauty_rows}")
    print(f"full_round_distinct: {full_rows}")
    print(f"screenshots_round65_main: {len(main_screenshots)}")
    print(f"screenshots_round65_extra: {len(extra_screenshots)}")
    if latest_shot:
        print(f"latest_screenshot_at: {datetime.fromtimestamp(latest_shot).isoformat(timespec='seconds')}")
    print("")
    print("shards:")
    for row in shard_rows:
        print(f"  {row['worker_name']}: {row['count_articles']} articles | last_update={row['updated_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
