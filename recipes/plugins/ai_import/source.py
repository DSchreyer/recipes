"""Fetching a recipe page and turning it into text a model can read.

Tandoor's own URL import (``POST /api/recipe-from-source/``) parses schema.org
and nothing else. That works on sites that publish it and produces the
"Spaghetti Carbonara - schnell & einfach" problem everywhere else, where the
page has no structured data and Tandoor falls back to whatever it can guess.

This module does not replace that import. It collects *source material*: the
page as readable text, so the model can structure a recipe that Tandoor alone
would have imported badly. The plugin never writes to the database; the
result goes back into Tandoor's own import dialog, which the household
reviews and saves.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

# A page worth sending is small. Anything bigger is a listing, not a recipe.
MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_SOURCE_CHARS = 24000
TIMEOUT_SECONDS = 20

# Stripped before text extraction: none of it is the recipe, and a model that
# sees a cookie banner sometimes quotes it back as an ingredient.
NOISE_TAGS = ('script', 'style', 'noscript', 'svg', 'iframe', 'form', 'nav',
              'header', 'footer', 'aside', 'template')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.5',
}


class FetchError(RuntimeError):
    """The page could not be fetched, or was not a page."""


def fetch_html(url: str) -> str:
    """Download a recipe page as text.

    Refuses anything that is not http(s): an importer that follows ``file://``
    or ``ftp://`` is a way to read the container's disk from the web UI.
    """
    if not re.match(r'^https?://', url or '', re.IGNORECASE):
        raise FetchError('Nur http(s)-Adressen')
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS, stream=True)
    except requests.exceptions.RequestException as exc:
        raise FetchError(f'Seite nicht erreichbar: {exc.__class__.__name__}') from exc

    if response.status_code != 200:
        raise FetchError(f'Seite antwortete mit {response.status_code}')

    content = response.raw.read(MAX_HTML_BYTES + 1, decode_content=True)
    if len(content) > MAX_HTML_BYTES:
        raise FetchError('Seite ist zu groß für einen Import')
    return content.decode(response.encoding or 'utf-8', errors='replace')


def html_to_text(html: str) -> str:
    """Readable text: title, then the body with navigation and scripts gone.

    Ordered by document position rather than by guessed selectors, because a
    recipe page that hides its ingredients in a tab still has them in the
    document, and a model reading the whole page is more reliable than a
    selector that matches on one site and misses on the next.
    """
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    title = (soup.title.get_text(strip=True) if soup.title else '')
    body = soup.body or soup
    lines = []
    for element in body.find_all(['h1', 'h2', 'h3', 'h4', 'li', 'p', 'td']):
        text = re.sub(r'\s+', ' ', element.get_text(' ', strip=True))
        if text:
            lines.append(text)

    text = '\n'.join(dict.fromkeys(lines))  # drop repeated nav lines
    if title:
        text = f'{title}\n\n{text}'
    return text[:MAX_SOURCE_CHARS]


def source_from_url(url: str) -> tuple[str, str]:
    """``(text, canonical_url)`` for a URL."""
    return html_to_text(fetch_html(url)), url


def source_from_text(text: str) -> str:
    return (text or '').strip()[:MAX_SOURCE_CHARS]
