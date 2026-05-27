"""page_monitor モジュールのユニットテスト。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import MonitoredPage, PageMonitorConfig
from app.page_monitor import (
    PageChangeResult,
    PageMonitorEntry,
    analyze_page,
    build_report_prompt,
    compute_content_hash,
    detect_changes,
    extract_links,
    fetch_page,
    parse_rss_feed,
)


# ────────────────────────────────────────────
# extract_links
# ────────────────────────────────────────────


class TestExtractLinks:
    def test_extracts_absolute_links(self):
        html = '<html><body><a href="https://example.com/article1">Article 1</a><a href="https://example.com/article2">Article 2</a></body></html>'
        links = extract_links(html, "https://example.com", "a")
        assert len(links) == 2
        assert links[0]["url"] == "https://example.com/article1"
        assert links[0]["text"] == "Article 1"

    def test_resolves_relative_links(self):
        html = '<html><body><a href="/articles/test">Test</a></body></html>'
        links = extract_links(html, "https://zenn.dev", "a")
        assert len(links) == 1
        assert links[0]["url"] == "https://zenn.dev/articles/test"

    def test_css_selector_filters(self):
        html = '<html><body><nav><a href="/nav">Nav</a></nav><article><a href="/art">Art</a></article></body></html>'
        links = extract_links(html, "https://example.com", "article a")
        assert len(links) == 1
        assert links[0]["url"] == "https://example.com/art"

    def test_deduplicates_links(self):
        html = '<html><body><a href="/a">A</a><a href="/a">A again</a></body></html>'
        links = extract_links(html, "https://example.com", "a")
        assert len(links) == 1

    def test_skips_empty_href(self):
        html = '<html><body><a href="">Empty</a><a>No href</a><a href="/valid">Valid</a></body></html>'
        links = extract_links(html, "https://example.com", "a")
        assert len(links) == 1
        assert links[0]["url"] == "https://example.com/valid"

    def test_skips_fragment_and_javascript(self):
        html = '<html><body><a href="#section">Frag</a><a href="javascript:void(0)">JS</a><a href="/real">Real</a></body></html>'
        links = extract_links(html, "https://example.com", "a")
        assert len(links) == 1
        assert links[0]["url"] == "https://example.com/real"


# ────────────────────────────────────────────
# compute_content_hash
# ────────────────────────────────────────────


class TestComputeContentHash:
    def test_same_content_same_hash(self):
        html = "<html><body><main>Hello World</main></body></html>"
        h1 = compute_content_hash(html, "main")
        h2 = compute_content_hash(html, "main")
        assert h1 == h2

    def test_different_content_different_hash(self):
        html1 = "<html><body><main>Hello</main></body></html>"
        html2 = "<html><body><main>World</main></body></html>"
        assert compute_content_hash(html1, "main") != compute_content_hash(html2, "main")

    def test_empty_selector_uses_body(self):
        html = "<html><body>Content here</body></html>"
        h = compute_content_hash(html, "")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_selector_not_found_hashes_full_body(self):
        html = "<html><body>Fallback</body></html>"
        h = compute_content_hash(html, "div.nonexistent")
        assert isinstance(h, str)
        assert len(h) == 64


# ────────────────────────────────────────────
# detect_changes
# ────────────────────────────────────────────


class TestDetectChanges:
    def _make_page(self, mode: str = "auto", **kwargs) -> MonitoredPage:
        defaults = dict(
            url="https://example.com",
            name="Test",
            mode=mode,
            link_selector="a",
            content_selector="main",
            enabled=True,
        )
        defaults.update(kwargs)
        return MonitoredPage(**defaults)

    def test_first_run_detects_all_as_new(self):
        page = self._make_page(mode="links")
        html = '<html><body><a href="/a">A</a><a href="/b">B</a></body></html>'
        prev = PageMonitorEntry()
        result = detect_changes(page, html, prev)
        assert result.has_changes is True
        assert len(result.new_links) == 2

    def test_no_changes_when_same_links(self):
        page = self._make_page(mode="links")
        html = '<html><body><a href="/a">A</a></body></html>'
        prev = PageMonitorEntry(known_links=["https://example.com/a"])
        result = detect_changes(page, html, prev)
        assert result.has_changes is False
        assert len(result.new_links) == 0

    def test_detects_new_link(self):
        page = self._make_page(mode="links")
        html = '<html><body><a href="/a">A</a><a href="/b">B</a></body></html>'
        prev = PageMonitorEntry(known_links=["https://example.com/a"])
        result = detect_changes(page, html, prev)
        assert result.has_changes is True
        assert len(result.new_links) == 1
        assert result.new_links[0]["url"] == "https://example.com/b"

    def test_content_mode_detects_change(self):
        page = self._make_page(mode="content")
        html = "<html><body><main>New content</main></body></html>"
        old_hash = compute_content_hash(
            "<html><body><main>Old content</main></body></html>", "main"
        )
        prev = PageMonitorEntry(content_hash=old_hash)
        result = detect_changes(page, html, prev)
        assert result.content_changed is True
        assert result.has_changes is True

    def test_content_mode_no_change(self):
        page = self._make_page(mode="content")
        html = "<html><body><main>Same</main></body></html>"
        same_hash = compute_content_hash(html, "main")
        prev = PageMonitorEntry(content_hash=same_hash)
        result = detect_changes(page, html, prev)
        assert result.content_changed is False
        assert result.has_changes is False

    def test_auto_mode_checks_both(self):
        page = self._make_page(mode="auto")
        html = '<html><body><main>Content</main><a href="/new">New</a></body></html>'
        old_hash = compute_content_hash(html, "main")  # same content
        prev = PageMonitorEntry(content_hash=old_hash, known_links=[])
        result = detect_changes(page, html, prev)
        assert result.has_changes is True  # new link detected
        assert len(result.new_links) == 1


# ────────────────────────────────────────────
# fetch_page (httpx mock)
# ────────────────────────────────────────────


class TestFetchPage:
    async def test_fetch_returns_html(self):
        mock_response = MagicMock()
        mock_response.text = "<html><body>OK</body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("app.page_monitor.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_page("https://example.com")
            assert result == "<html><body>OK</body></html>"

    async def test_fetch_raises_on_error(self):
        import httpx

        with patch("app.page_monitor.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "404", request=MagicMock(), response=MagicMock()
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await fetch_page("https://example.com/404")


# ────────────────────────────────────────────
# build_report_prompt
# ────────────────────────────────────────────


class TestBuildReportPrompt:
    def _make_page(self, **kwargs) -> MonitoredPage:
        defaults = dict(
            url="https://example.com",
            name="Test Page",
            mode="links",
            link_selector="a",
            content_selector="",
            enabled=True,
        )
        defaults.update(kwargs)
        return MonitoredPage(**defaults)

    def test_includes_page_name_and_url(self):
        page = self._make_page(name="My Page", url="https://example.com")
        change = PageChangeResult(
            page=page,
            content_changed=False,
            new_links=[{"url": "https://example.com/new", "text": "New Article"}],
            has_changes=True,
        )
        prompt = build_report_prompt([change])
        assert "My Page" in prompt
        assert "https://example.com" in prompt
        assert "https://example.com/new" in prompt
        assert "New Article" in prompt

    def test_multiple_pages(self):
        page1 = self._make_page(name="Page 1", url="https://a.com")
        page2 = self._make_page(name="Page 2", url="https://b.com")
        changes = [
            PageChangeResult(
                page=page1,
                content_changed=False,
                new_links=[{"url": "https://a.com/1", "text": "A1"}],
                has_changes=True,
            ),
            PageChangeResult(
                page=page2,
                content_changed=True,
                new_links=[],
                has_changes=True,
            ),
        ]
        prompt = build_report_prompt(changes)
        assert "Page 1" in prompt
        assert "Page 2" in prompt

    def test_empty_changes_returns_empty(self):
        prompt = build_report_prompt([])
        assert prompt == ""

    def test_content_changed_noted(self):
        page = self._make_page(name="Updated Page")
        change = PageChangeResult(
            page=page, content_changed=True, new_links=[], has_changes=True
        )
        prompt = build_report_prompt([change])
        assert "Updated Page" in prompt


# ────────────────────────────────────────────
# Config round-trip for PageMonitorConfig
# ────────────────────────────────────────────


class TestPageMonitorConfigRoundTrip:
    def test_default_roundtrip(self):
        from app.config import AppConfig, _app_config_to_dict, _dict_to_app_config

        config = AppConfig()
        d = _app_config_to_dict(config)
        restored = _dict_to_app_config(d)
        assert restored.page_monitor.enabled is False
        assert restored.page_monitor.pages == []

    def test_with_pages_roundtrip(self):
        from app.config import AppConfig, _app_config_to_dict, _dict_to_app_config

        config = AppConfig(
            page_monitor=PageMonitorConfig(
                enabled=True,
                pages=[
                    MonitoredPage(
                        url="https://zenn.dev/p/microsoft",
                        name="Zenn Microsoft",
                        mode="links",
                        link_selector="article a",
                        analyzed=True,
                    ),
                    MonitoredPage(
                        url="https://code.visualstudio.com/updates",
                        name="VS Code Updates",
                        mode="content",
                        content_selector="main",
                        analyzed=True,
                    ),
                ],
            )
        )
        d = _app_config_to_dict(config)
        restored = _dict_to_app_config(d)
        assert restored.page_monitor.enabled is True
        assert len(restored.page_monitor.pages) == 2
        assert restored.page_monitor.pages[0].url == "https://zenn.dev/p/microsoft"
        assert restored.page_monitor.pages[0].mode == "links"
        assert restored.page_monitor.pages[1].content_selector == "main"
        assert restored.page_monitor.pages[0].analyzed is True


# ────────────────────────────────────────────
# State round-trip for page_monitor_state
# ────────────────────────────────────────────


class TestPageMonitorStateRoundTrip:
    def test_default_roundtrip(self):
        from app.state_manager import AppState, _app_state_to_dict, _dict_to_app_state

        state = AppState()
        d = _app_state_to_dict(state)
        restored = _dict_to_app_state(d)
        assert restored.page_monitor_state == {}
        assert restored.run_count_c == 0
        assert restored.last_run_c_at == ""

    def test_with_monitor_state(self):
        from app.state_manager import AppState, _app_state_to_dict, _dict_to_app_state

        state = AppState(
            run_count_c=3,
            last_run_c_at="2026-04-06T09:00:00",
            page_monitor_state={
                "https://example.com": PageMonitorEntry(
                    content_hash="abc123",
                    known_links=[
                        "https://example.com/a",
                        "https://example.com/b",
                    ],
                    last_checked_at="2026-04-06T09:00:00",
                ),
            },
        )
        d = _app_state_to_dict(state)
        restored = _dict_to_app_state(d)
        assert restored.run_count_c == 3
        assert restored.last_run_c_at == "2026-04-06T09:00:00"
        assert "https://example.com" in restored.page_monitor_state
        entry = restored.page_monitor_state["https://example.com"]
        assert entry.content_hash == "abc123"
        assert len(entry.known_links) == 2

    def test_state_manager_increment_c(self):
        from app.state_manager import AppState, StateManager

        sm = StateManager.__new__(StateManager)
        sm._state = AppState()
        sm._path = None  # type: ignore[assignment]
        sm.increment_run_count("c")
        assert sm.state.run_count_c == 1

    def test_state_manager_update_page_monitor_state(self):
        from app.state_manager import AppState, StateManager

        sm = StateManager.__new__(StateManager)
        sm._state = AppState()
        sm._path = None  # type: ignore[assignment]
        entry = PageMonitorEntry(
            content_hash="hash1",
            known_links=["https://example.com/a"],
            last_checked_at="2026-04-06T09:00:00",
        )
        sm.update_page_monitor_state("https://example.com", entry)
        assert "https://example.com" in sm.state.page_monitor_state
        assert sm.state.page_monitor_state["https://example.com"].content_hash == "hash1"


# ────────────────────────────────────────────
# analyze_page (自動分析)
# ────────────────────────────────────────────


class TestAnalyzePage:
    async def test_detects_rss_link_tag(self):
        html = '''<html><head>
            <title>My Blog</title>
            <link rel="alternate" type="application/rss+xml" href="/feed.xml">
        </head><body><main>Content</main></body></html>'''

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.page_monitor.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await analyze_page("https://example.com")
            assert result.mode == "rss"
            assert result.feed_url == "https://example.com/feed.xml"
            assert result.name == "My Blog"
            assert result.analyzed is True

    async def test_detects_atom_link_tag(self):
        html = '''<html><head>
            <title>Atom Blog</title>
            <link rel="alternate" type="application/atom+xml" href="/atom.xml">
        </head><body></body></html>'''

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.page_monitor.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await analyze_page("https://example.com")
            assert result.mode == "rss"
            assert result.feed_url == "https://example.com/atom.xml"

    async def test_detects_rss_xml_directly(self):
        xml_content = '<?xml version="1.0"?><rss><channel><title>Direct RSS</title></channel></rss>'

        mock_resp = MagicMock()
        mock_resp.text = xml_content
        mock_resp.headers = {"content-type": "application/xml"}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.page_monitor.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await analyze_page("https://example.com/feed.xml")
            assert result.mode == "rss"
            assert result.feed_url == "https://example.com/feed.xml"
            assert result.name == "Direct RSS"

    async def test_links_mode_for_link_heavy_page(self):
        links = "".join(f'<a href="/article/{i}">Article {i}</a>' for i in range(15))
        html = f"<html><head><title>News Site</title></head><body><main>{links}</main></body></html>"

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.page_monitor.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await analyze_page("https://example.com")
            assert result.mode == "links"
            assert result.link_selector != ""
            assert result.name == "News Site"
            assert result.analyzed is True

    async def test_content_mode_for_few_links(self):
        html = "<html><head><title>Docs Page</title></head><body><main><p>Long content here.</p><a href='/one'>Link</a></main></body></html>"

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.page_monitor.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await analyze_page("https://example.com")
            assert result.mode == "content"
            assert result.content_selector != ""
            assert result.analyzed is True

    async def test_extracts_title(self):
        html = "<html><head><title>  Test Title  </title></head><body><main>X</main></body></html>"

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.page_monitor.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await analyze_page("https://example.com")
            assert result.name == "Test Title"


# ────────────────────────────────────────────
# parse_rss_feed
# ────────────────────────────────────────────


class TestParseRssFeed:
    def test_parses_rss2(self):
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Blog</title>
            <item><title>Post 1</title><link>https://example.com/post1</link></item>
            <item><title>Post 2</title><link>https://example.com/post2</link></item>
        </channel></rss>"""
        items = parse_rss_feed(xml)
        assert len(items) == 2
        assert items[0]["url"] == "https://example.com/post1"
        assert items[0]["text"] == "Post 1"

    def test_parses_atom(self):
        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>Atom Blog</title>
            <entry><title>Entry 1</title><link href="https://example.com/e1"/></entry>
            <entry><title>Entry 2</title><link href="https://example.com/e2"/></entry>
        </feed>"""
        items = parse_rss_feed(xml)
        assert len(items) == 2
        assert items[0]["url"] == "https://example.com/e1"
        assert items[0]["text"] == "Entry 1"

    def test_empty_feed(self):
        xml = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        items = parse_rss_feed(xml)
        assert items == []

    def test_invalid_xml_returns_empty(self):
        items = parse_rss_feed("not xml at all")
        assert items == []


# ────────────────────────────────────────────
# detect_changes with RSS mode
# ────────────────────────────────────────────


class TestDetectChangesRss:
    def test_rss_mode_detects_new_entries(self):
        page = MonitoredPage(
            url="https://example.com",
            name="Test",
            mode="rss",
            feed_url="https://example.com/feed.xml",
            analyzed=True,
        )
        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
            <item><title>Old</title><link>https://example.com/old</link></item>
            <item><title>New</title><link>https://example.com/new</link></item>
        </channel></rss>"""
        prev = PageMonitorEntry(known_links=["https://example.com/old"])
        result = detect_changes(page, rss_xml, prev)
        assert result.has_changes is True
        assert len(result.new_links) == 1
        assert result.new_links[0]["url"] == "https://example.com/new"

    def test_rss_mode_no_changes(self):
        page = MonitoredPage(
            url="https://example.com",
            name="Test",
            mode="rss",
            feed_url="https://example.com/feed.xml",
            analyzed=True,
        )
        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
            <item><title>Old</title><link>https://example.com/old</link></item>
        </channel></rss>"""
        prev = PageMonitorEntry(known_links=["https://example.com/old"])
        result = detect_changes(page, rss_xml, prev)
        assert result.has_changes is False


# ────────────────────────────────────────────
# Config round-trip with new fields
# ────────────────────────────────────────────


class TestPageMonitorConfigRoundTripV2:
    def test_url_only_roundtrip(self):
        from app.config import AppConfig, _app_config_to_dict, _dict_to_app_config

        config = AppConfig(
            page_monitor=PageMonitorConfig(
                enabled=True,
                pages=[MonitoredPage(url="https://example.com")],
            )
        )
        d = _app_config_to_dict(config)
        restored = _dict_to_app_config(d)
        assert restored.page_monitor.pages[0].url == "https://example.com"
        assert restored.page_monitor.pages[0].analyzed is False
        assert restored.page_monitor.pages[0].feed_url == ""

    def test_analyzed_page_roundtrip(self):
        from app.config import AppConfig, _app_config_to_dict, _dict_to_app_config

        config = AppConfig(
            page_monitor=PageMonitorConfig(
                enabled=True,
                pages=[
                    MonitoredPage(
                        url="https://example.com/feed",
                        name="RSS Site",
                        mode="rss",
                        feed_url="https://example.com/feed.xml",
                        analyzed=True,
                    ),
                ],
            )
        )
        d = _app_config_to_dict(config)
        restored = _dict_to_app_config(d)
        p = restored.page_monitor.pages[0]
        assert p.mode == "rss"
        assert p.feed_url == "https://example.com/feed.xml"
        assert p.analyzed is True


# ────────────────────────────────────────────
# parse_rss_feed edge cases
# ────────────────────────────────────────────


class TestParseRssFeedEdgeCases:
    def test_item_without_link_skipped(self):
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
            <item><title>No Link</title></item>
            <item><title>Has Link</title><link>https://example.com/ok</link></item>
        </channel></rss>"""
        items = parse_rss_feed(xml)
        assert len(items) == 1
        assert items[0]["url"] == "https://example.com/ok"

    def test_item_with_empty_link_skipped(self):
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
            <item><title>Empty</title><link>  </link></item>
            <item><title>Good</title><link>https://example.com/good</link></item>
        </channel></rss>"""
        items = parse_rss_feed(xml)
        assert len(items) == 1

    def test_item_with_empty_title(self):
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
            <item><title></title><link>https://example.com/notitle</link></item>
        </channel></rss>"""
        items = parse_rss_feed(xml)
        assert len(items) == 1
        assert items[0]["text"] == ""
        assert items[0]["url"] == "https://example.com/notitle"
