#!/usr/bin/env python3
"""
Export Luma Learning Center articles to one plain-text file per article.

What it does:
1. Opens https://lumalabs.ai/learning-center/articles.
2. Discovers every /learning-center/articles/... link it can see.
3. Optionally uses Playwright to catch client-side/rendered links.
4. Fetches each article.
5. Extracts readable main article text.
6. Saves one .txt file per article.
7. Writes a manifest.csv with title, URL, output filename, and word count.

Recommended:
    python -m pip install -r requirements.txt
    python export_luma_learning_center_articles.py

For browser-rendered discovery:
    python -m playwright install chromium
    python export_luma_learning_center_articles.py --browser

If the page truly has 40 articles in your logged-out browser, --browser is the better mode.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

INDEX_URL = "https://lumalabs.ai/learning-center/articles"
OUT_DIR = Path("luma_learning_center_plain_text_articles")

SEEDED_ARTICLES = [
    ("Credit Conservation", "https://lumalabs.ai/learning-center/articles/credit-conservation"),
    ("Color Space Field Guide", "https://lumalabs.ai/learning-center/articles/color-space-field-guide"),
    ("Uni-1 Field Guide", "https://lumalabs.ai/learning-center/articles/luma-uni-1-field-guide"),
    ("Starting Points", "https://lumalabs.ai/learning-center/articles/starting-points"),
    ("Uni-1", "https://lumalabs.ai/learning-center/articles/luma-uni-1-model"),
    ("The Luma Agent", "https://lumalabs.ai/learning-center/articles/about-the-luma-agent"),
    ("Just Ask The Agent", "https://lumalabs.ai/learning-center/articles/ask-the-agent"),
    ("Avoiding Common Mistakes", "https://lumalabs.ai/learning-center/articles/avoiding-common-mistakes"),
    ("Brainstorm Mode", "https://lumalabs.ai/learning-center/articles/brainstorm-mode"),
    ("Character and Object Consistency", "https://lumalabs.ai/learning-center/articles/character-and-object-consistency"),
    ("Creating At Scale in Luma", "https://lumalabs.ai/learning-center/articles/creating-at-scale-in-luma"),
    ("Endless Variations", "https://lumalabs.ai/learning-center/articles/endless-variants"),
    ("Luma Audio Capabilities", "https://lumalabs.ai/learning-center/articles/luma-audio-capabilities"),
    ("Luma Image Capabilities", "https://lumalabs.ai/learning-center/articles/luma-image-capabilities"),
    ("Luma Image Models Field Guide", "https://lumalabs.ai/learning-center/articles/luma-image-models-field-guide"),
    ("Luma Lip Sync Guide", "https://lumalabs.ai/learning-center/articles/luma-lip-sync-field-guide"),
    ("Luma Toolbar Field Guide", "https://lumalabs.ai/learning-center/articles/luma-toolbar-field-guide"),
    ("Luma Video Capabilities", "https://lumalabs.ai/learning-center/articles/luma-video-capabilities"),
    ("Luma Video Models Field Guide", "https://lumalabs.ai/learning-center/articles/luma-video-models-field-guide"),
    ("Master Reference Assets", "https://lumalabs.ai/learning-center/articles/master-reference-assets"),
    ("Outcome-First Workflow", "https://lumalabs.ai/learning-center/articles/outcome-first-workflow"),
    ("Research with Luma", "https://lumalabs.ai/learning-center/articles/research-with-luma"),
    ("Team Collaboration in Luma", "https://lumalabs.ai/learning-center/articles/team-collaboration-in-luma"),
    ("Text & Natural Language", "https://lumalabs.ai/learning-center/articles/text-and-natural-language"),
    ("Talk To The Agent", "https://lumalabs.ai/learning-center/articles/treat-the-agent-like-a-teammate"),
    ("Turn Your Files Into Creative Assets", "https://lumalabs.ai/learning-center/articles/turn-your-files-into-creative-assets"),
    ("Using Master References", "https://lumalabs.ai/learning-center/articles/using-master-references"),
    ("Welcome To Luma Agents", "https://lumalabs.ai/learning-center/articles/welcome-to-luma-agents"),
]


def slugify(text: str, fallback: str = "article") -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text or fallback


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
    )
    return s


def fetch_html(session: requests.Session, url: str, timeout: int = 30) -> str:
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def discover_with_requests(session: requests.Session) -> list[tuple[str, str]]:
    html = fetch_html(session, INDEX_URL)
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}

    for a in soup.select('a[href*="/learning-center/articles/"]'):
        href = a.get("href")
        if not href:
            continue
        url = clean_url(urljoin(INDEX_URL, href))
        if url.rstrip("/") == INDEX_URL.rstrip("/"):
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
        found[url] = title

    return [(title, url) for url, title in sorted(found.items())]


def discover_with_playwright() -> list[tuple[str, str]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is not installed. Run: python -m pip install playwright && "
            "python -m playwright install chromium"
        ) from exc

    found: dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1800})
        page.goto(INDEX_URL, wait_until="networkidle", timeout=60000)

        # Try to expose lazy-loaded cards.
        for _ in range(8):
            page.mouse.wheel(0, 2400)
            page.wait_for_timeout(800)

        # Try filter tabs in case each tab reveals a different subset.
        for label in ["All", "Capabilities", "Get Started", "Workflow"]:
            try:
                page.get_by_text(label, exact=True).click(timeout=2000)
                page.wait_for_timeout(1000)
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(500)
            except Exception:
                pass

        links = page.locator('a[href*="/learning-center/articles/"]')
        for i in range(links.count()):
            a = links.nth(i)
            href = a.get_attribute("href")
            if not href:
                continue
            url = clean_url(urljoin(INDEX_URL, href))
            if url.rstrip("/") == INDEX_URL.rstrip("/"):
                continue
            title = a.inner_text().strip() or url.rstrip("/").split("/")[-1].replace("-", " ").title()
            found[url] = re.sub(r"\s+", " ", title)

        browser.close()

    return [(title, url) for url, title in sorted(found.items())]


def extract_article_text(html: str, url: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        bad.decompose()

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)

    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True).replace("| Luma", "").strip()

    # Prefer semantic containers, fall back to body.
    candidates = []
    for selector in ["article", "main", "[role='main']", "body"]:
        for node in soup.select(selector):
            txt = node.get_text("\n", strip=True)
            if txt:
                candidates.append((len(txt), node))

    if not candidates:
        return title or "Untitled", ""

    node = max(candidates, key=lambda x: x[0])[1]

    lines: list[str] = []
    block_tags = ["h1", "h2", "h3", "h4", "p", "li", "pre", "code", "blockquote"]

    for el in node.find_all(block_tags):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue

        # Remove common global nav/footer clutter.
        if txt in {
            "Product", "Pricing", "API", "Enterprise", "News", "Join us", "Sign In",
            "Use Cases", "UNI-1", "Join Us", "Creative Partner Program",
            "Education Program", "Learning Center", "Media kit", "Terms of Service",
            "Privacy Policy", "Cookie Policy", "Subprocessors", "Luma"
        }:
            continue

        if el.name in {"h1", "h2"}:
            lines.append("\n" + txt + "\n" + ("=" * min(len(txt), 80)))
        elif el.name in {"h3", "h4"}:
            lines.append("\n" + txt + "\n" + ("-" * min(len(txt), 80)))
        elif el.name == "li":
            lines.append(f"- {txt}")
        else:
            lines.append(txt)

    cleaned: list[str] = []
    previous = None
    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if line == previous:
            continue
        cleaned.append(line)
        previous = line

    text = "\n\n".join(cleaned).strip()

    # Add source header.
    if title:
        header = f"{title}\nSource: {url}\n\n"
        if not text.startswith(title):
            text = header + text
        else:
            text = f"Source: {url}\n\n{text}"
    else:
        text = f"Source: {url}\n\n{text}"

    return title or url.rstrip("/").split("/")[-1].replace("-", " ").title(), text


def merge_article_lists(*lists: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: dict[str, str] = {}
    for items in lists:
        for title, url in items:
            url = clean_url(url)
            if "/learning-center/articles/" not in url:
                continue
            merged[url] = title
    return [(title, url) for url, title in sorted(merged.items())]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Use Playwright browser discovery.")
    parser.add_argument("--seed-only", action="store_true", help="Use the built-in URL seed list only.")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = get_session()

    discovered: list[tuple[str, str]] = []
    if args.seed_only:
        discovered = SEEDED_ARTICLES
    else:
        try:
            discovered = discover_with_requests(session)
        except Exception as exc:
            print(f"Requests discovery failed: {exc}", file=sys.stderr)

        if args.browser:
            browser_found = discover_with_playwright()
            discovered = merge_article_lists(discovered, browser_found)

        discovered = merge_article_lists(SEEDED_ARTICLES, discovered)

    print(f"Discovered {len(discovered)} article URLs.")

    manifest_rows = []
    used_filenames: set[str] = set()

    for idx, (seed_title, url) in enumerate(discovered, start=1):
        print(f"[{idx:02d}/{len(discovered):02d}] Fetching {url}")
        try:
            html = fetch_html(session, url)
            title, text = extract_article_text(html, url)
            title = title or seed_title
            base_name = f"{idx:02d}_{slugify(title)}.txt"
            filename = base_name
            n = 2
            while filename in used_filenames:
                filename = f"{idx:02d}_{slugify(title)}_{n}.txt"
                n += 1
            used_filenames.add(filename)
            path = out_dir / filename
            path.write_text(text.strip() + "\n", encoding="utf-8")
            word_count = len(re.findall(r"\b\w+\b", text))
            manifest_rows.append(
                {
                    "index": idx,
                    "title": title,
                    "url": url,
                    "filename": filename,
                    "word_count": word_count,
                    "status": "ok",
                }
            )
            time.sleep(0.2)
        except Exception as exc:
            filename = f"{idx:02d}_{slugify(seed_title)}__ERROR.txt"
            (out_dir / filename).write_text(
                f"{seed_title}\nSource: {url}\n\nERROR: {exc}\n",
                encoding="utf-8",
            )
            manifest_rows.append(
                {
                    "index": idx,
                    "title": seed_title,
                    "url": url,
                    "filename": filename,
                    "word_count": 0,
                    "status": f"error: {exc}",
                }
            )

    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["index", "title", "url", "filename", "word_count", "status"]
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\nDone. Wrote {len(manifest_rows)} files to: {out_dir.resolve()}")
    print(f"Manifest: {manifest_path.resolve()}")

    expected = 40
    if len(discovered) != expected:
        print(
            f"\nNote: expected {expected} based on your note, but discovered {len(discovered)}. "
            "Run again with --browser if you have not already. If it still finds fewer, "
            "the public article index may currently expose fewer than 40 article URLs."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
