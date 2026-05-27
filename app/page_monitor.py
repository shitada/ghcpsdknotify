"""ページモニター — Web ページの更新検出コアモジュール。

監視対象ページの HTML を取得し、リンクの追加やコンテンツの変更を検出する。
RSS/Atom フィードの検出・パースにも対応する。
検出結果は Copilot SDK 用のユーザープロンプトとして構築される。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import MonitoredPage

logger = logging.getLogger(__name__)


@dataclass
class PageMonitorEntry:
    """ページモニターの1ページ分の状態。"""

    content_hash: str = ""
    known_links: list[str] = field(default_factory=list)
    last_checked_at: str = ""


@dataclass
class PageChangeResult:
    """1ページ分の変更検出結果。"""

    page: MonitoredPage
    content_changed: bool = False
    new_links: list[dict[str, str]] = field(default_factory=list)
    has_changes: bool = False


async def fetch_page(url: str, timeout: int = 30, max_retries: int = 3) -> str:
    """指定 URL の HTML を取得する。ネットワークエラー時はリトライする。

    Args:
        url: 取得先 URL。
        timeout: タイムアウト秒数。
        max_retries: 最大リトライ回数（初回試行を含まない）。

    Returns:
        HTML テキスト。

    Raises:
        httpx.HTTPStatusError: HTTP エラー時（リトライしない）。
        httpx.RequestError: 全リトライ失敗後。
    """
    _RETRY_DELAYS = [5, 15, 30]  # 秒

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "ghcpsdknotify-page-monitor/1.0"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError:
            # 4xx/5xx はリトライしない
            raise
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                logger.warning(
                    "ページ取得失敗 (試行 %d/%d, %s): %s — %d秒後にリトライします",
                    attempt + 1, max_retries + 1, url, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "ページ取得失敗 (試行 %d/%d, %s): %s — リトライ上限に達しました",
                    attempt + 1, max_retries + 1, url, exc,
                )

    assert last_exc is not None
    raise last_exc


def extract_links(html: str, base_url: str, selector: str) -> list[dict[str, str]]:
    """HTML からリンクを抽出する。

    Args:
        html: HTML テキスト。
        base_url: 相対 URL 解決用のベース URL。
        selector: CSS セレクタ（例: "a", "article a"）。

    Returns:
        [{"url": "...", "text": "..."}, ...] の重複除去済みリスト。
    """
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.select(selector)

    seen: set[str] = set()
    links: list[dict[str, str]] = []

    for el in elements:
        href = el.get("href", "")
        if not href or not isinstance(href, str):
            continue

        # フラグメントのみ・javascript: スキーム をスキップ
        href = href.strip()
        if href.startswith("#") or href.startswith("javascript:"):
            continue

        # 相対 URL → 絶対 URL
        full_url = urljoin(base_url, href)

        if full_url in seen:
            continue
        seen.add(full_url)

        text = el.get_text(strip=True)
        links.append({"url": full_url, "text": text})

    return links


def compute_content_hash(html: str, selector: str) -> str:
    """HTML の指定セレクタ内テキストの SHA-256 ハッシュを計算する。

    Args:
        html: HTML テキスト。
        selector: CSS セレクタ。空文字列の場合は body 全体を使用。

    Returns:
        SHA-256 ハッシュ（16進数、64文字）。
    """
    soup = BeautifulSoup(html, "html.parser")

    target = None
    if selector:
        target = soup.select_one(selector)

    if target is None:
        target = soup.body or soup

    text = target.get_text(strip=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_changes(
    page: MonitoredPage,
    html: str,
    prev_state: PageMonitorEntry,
) -> PageChangeResult:
    """ページの変更を検出する。

    Args:
        page: 監視対象ページの設定。
        html: 取得した HTML テキスト（RSS モードの場合は XML テキスト）。
        prev_state: 前回の PageMonitorEntry（初回は空の状態）。

    Returns:
        PageChangeResult — 変更有無とその詳細。
    """
    result = PageChangeResult(page=page)

    # RSS モード
    if page.mode == "rss":
        entries = parse_rss_feed(html)
        known_set = set(prev_state.known_links)
        new_links = [e for e in entries if e["url"] not in known_set]
        result.new_links = new_links
        if new_links:
            result.has_changes = True
        return result

    # リンクモード or 自動モード
    if page.mode in ("links", "auto"):
        selector = page.link_selector or "a"
        current_links = extract_links(html, page.url, selector)
        known_set = set(prev_state.known_links)
        new_links = [link for link in current_links if link["url"] not in known_set]
        result.new_links = new_links
        if new_links:
            result.has_changes = True

    # コンテンツモード or 自動モード
    if page.mode in ("content", "auto"):
        current_hash = compute_content_hash(html, page.content_selector)
        if prev_state.content_hash and current_hash != prev_state.content_hash:
            result.content_changed = True
            result.has_changes = True
        elif not prev_state.content_hash:
            pass

    return result


def parse_rss_feed(xml_text: str) -> list[dict[str, str]]:
    """RSS 2.0 / Atom フィードをパースしてエントリ一覧を返す。

    Args:
        xml_text: RSS/Atom の XML テキスト。

    Returns:
        [{"url": "...", "text": "..."}, ...] のリスト。パース失敗時は空リスト。
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("RSS/Atom XML のパースに失敗しました")
        return []

    items: list[dict[str, str]] = []

    # RSS 2.0: <rss><channel><item>
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        if link:
            items.append({"url": link, "text": title})

    if items:
        return items

    # Atom: <feed><entry>
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link = link_el.get("href", "").strip() if link_el is not None else ""
        if link:
            items.append({"url": link, "text": title})

    return items


async def analyze_page(url: str, timeout: int = 30) -> MonitoredPage:
    """URL を取得して最適な監視戦略を自動判定する。

    判定順序:
    1. Content-Type が XML → RSS 直接 URL
    2. HTML 内の <link rel="alternate" type="application/rss+xml"> → RSS フィード
    3. HTML 分析: リンク密度で links / content モード判定

    Args:
        url: 監視対象 URL。
        timeout: タイムアウト秒数。

    Returns:
        分析済みの MonitoredPage。
    """
    page = MonitoredPage(url=url, enabled=True)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "ghcpsdknotify-page-monitor/1.0"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    text = response.text

    # 1. Content-Type が XML → RSS 直接 URL
    if "xml" in content_type or "rss" in content_type or "atom" in content_type:
        page.mode = "rss"
        page.feed_url = url
        # RSS からタイトル取得
        try:
            root = ET.fromstring(text)
            # RSS 2.0
            channel_title = root.find(".//channel/title")
            if channel_title is not None and channel_title.text:
                page.name = channel_title.text.strip()
            else:
                # Atom
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                feed_title = root.find("atom:title", ns)
                if feed_title is not None and feed_title.text:
                    page.name = feed_title.text.strip()
        except ET.ParseError:
            pass
        page.name = page.name or url
        page.analyzed = True
        return page

    # 2. HTML パース
    soup = BeautifulSoup(text, "html.parser")

    # タイトル取得
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        page.name = title_tag.string.strip()
    else:
        page.name = url

    # RSS/Atom フィード検出 (<link rel="alternate">)
    for link_tag in soup.find_all("link", rel="alternate"):
        link_type = (link_tag.get("type") or "").lower()
        if "rss" in link_type or "atom" in link_type:
            href = link_tag.get("href", "")
            if href:
                page.mode = "rss"
                page.feed_url = urljoin(url, href)
                page.analyzed = True
                return page

    # 3. HTML 分析: コンテンツ領域を特定してリンク密度で判定
    content_area = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    if content_area:
        content_selector = content_area.name
        links_in_content = content_area.find_all("a", href=True)
    else:
        content_selector = "body"
        body = soup.find("body") or soup
        links_in_content = body.find_all("a", href=True)

    link_count = len(links_in_content)

    if link_count >= 10:
        page.mode = "links"
        # セレクタ推定: コンテンツ領域内のリンク
        if content_area and content_area.name != "body":
            page.link_selector = f"{content_area.name} a"
        else:
            page.link_selector = "a"
    else:
        page.mode = "content"
        page.content_selector = content_selector

    page.analyzed = True
    return page


def build_report_prompt(changes: list[PageChangeResult]) -> str:
    """変更検出結果からユーザープロンプトを構築する。

    Args:
        changes: 変更があったページの PageChangeResult リスト。

    Returns:
        Copilot SDK に送信するユーザープロンプト文字列。変更なしの場合は空文字列。
    """
    if not changes:
        return ""

    sections: list[str] = []

    for change in changes:
        page = change.page
        parts: list[str] = []
        parts.append(f"## {page.name} ({page.url})")

        if change.new_links:
            parts.append("")
            parts.append("### 新しいリンク")
            for link in change.new_links:
                parts.append(f"- [{link['text']}]({link['url']})")

        if change.content_changed:
            parts.append("")
            parts.append("### コンテンツ更新")
            parts.append(f"ページのコンテンツが更新されました: {page.url}")

        sections.append("\n".join(parts))

    header = (
        "以下の監視対象ページで更新が検出されました。\n\n"
        "**重要**: 各リンク先の記事について、必ず Bing Web 検索を使って記事の詳細を取得し、"
        "著者・投稿日・本文のポイントを含む詳細な要約を作成してください。"
        "タイトルと URL だけのリストにしないでください。\n"
    )
    return header + "\n\n".join(sections)
