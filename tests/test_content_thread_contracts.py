from pathlib import Path


def test_microblog_comment_route_resolves_thread_root_before_persisting():
    source = (Path(__file__).resolve().parents[1] / "y_server/routes/content_management.py").read_text(encoding="utf-8")

    assert "def _resolve_thread_root_id(post):" in source
    assert "thread_id = _resolve_thread_root_id(post)" in source
    assert "thread_id=thread_id" in source


def test_microblog_thread_lookup_routes_use_resolved_thread_root():
    source = (Path(__file__).resolve().parents[1] / "y_server/routes/content_management.py").read_text(encoding="utf-8")

    assert "select(Post).filter_by(thread_id=thread_root_id)" in source
    assert "return json.dumps(_resolve_thread_root_id(post))" in source
