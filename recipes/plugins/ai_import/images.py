"""Picking the page's own photos for the import draft.

The editor already asks "which photo?" when the draft carries several. All this
module has to decide is which URLs are worth offering.

No image is fetched here. An import that downloads twelve candidates to measure
them turns a five-second request into a minute, and the editor fetches the one
that is actually chosen. The heuristics are URL-level on purpose:

* ``og:image`` and ``twitter:image`` first -- that is the image the site itself
  chose to represent the page, and on recipe sites it is the finished dish;
* then ``img`` tags in document order, ``srcset`` and ``data-src`` included
  because lazy loading hides the real URL behind them;
* commercials and buttons are dropped by filename, which is what they are
  called on every site.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

MAX_IMAGES = 12

# Filenames that are almost never the dish.
NOISE = re.compile(
    r'(logo|icon|sprite|avatar|favicon|banner|ads?[-_]|sponsor|pixel|placeholder'
    r'|button|arrow|chevron|share|facebook|instagram|pinterest|whatsapp|youtube)',
    re.IGNORECASE)

IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.webp', '.avif')


def _absolute(url: str, base: str) -> str | None:
    if not url:
        return None
    url = url.strip().split(' ')[0].split(',')[0]  # srcset: "a.jpg 1x, b.jpg 2x"
    if url.startswith('//'):
        url = 'https:' + url
    if url.startswith('data:'):
        return None
    absolute = urljoin(base, url)
    scheme = urlparse(absolute).scheme
    if scheme not in ('http', 'https'):
        return None
    return absolute


def _looks_like_photo(url: str) -> bool:
    path = urlparse(url).path.lower()
    if NOISE.search(path):
        return False
    return path.endswith(IMAGE_SUFFIXES)


def images_from_html(html: str, base_url: str) -> list[str]:
    """Up to ``MAX_IMAGES`` photo URLs, best first."""
    soup = BeautifulSoup(html, 'html.parser')
    found: list[str] = []

    def add(raw: str | None) -> None:
        absolute = _absolute(raw or '', base_url)
        if absolute and _looks_like_photo(absolute) and absolute not in found:
            found.append(absolute)

    for prop in ('og:image', 'og:image:url', 'twitter:image'):
        for tag in soup.find_all('meta', attrs={'property': prop}) + soup.find_all('meta', attrs={'name': prop}):
            add(tag.get('content'))

    for img in soup.find_all('img'):
        for attribute in ('src', 'data-src', 'data-lazy-src', 'srcset', 'data-srcset'):
            add(img.get(attribute))
        if len(found) >= MAX_IMAGES:
            break

    return found[:MAX_IMAGES]
