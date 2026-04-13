from backend.services.summary_preview_service import (
    is_summary_preview_html,
    render_summary_preview_html,
)


def test_render_summary_preview_html_marks_document():
    html = render_summary_preview_html("## Key Point\n\nAlpha paragraph", language="zh")

    assert html is not None
    assert "summary-preview-shell" in html
    assert 'data-summary-preview="true"' in html
    assert "<h2" in html
    assert "Alpha paragraph" in html


def test_is_summary_preview_html_rejects_unmarked_html():
    assert not is_summary_preview_html("<html><body><p>plain</p></body></html>")


def test_render_summary_preview_html_returns_none_for_blank_input():
    assert render_summary_preview_html("   ", language="en") is None
