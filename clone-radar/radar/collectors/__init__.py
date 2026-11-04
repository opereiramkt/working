"""Coletores da Biblioteca de Anúncios da Meta.

Todos devolvem uma lista de `Ad` normalizados. O formato "snapshot" é o mesmo
usado internamente pela Biblioteca (e pelos scrapers do Apify), então um único
normalizador cobre o Apify e a raspagem via Playwright.
"""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from ..models import Ad

log = logging.getLogger(__name__)

LIB = "https://www.facebook.com/ads/library/"


def keyword_url(term: str, country: str, active_only: bool) -> str:
    return LIB + "?" + urlencode({
        "active_status": "active" if active_only else "all",
        "ad_type": "all",
        "country": country,
        "q": term,
        "search_type": "keyword_unordered",
        "media_type": "all",
    })


def page_url(page_id: str, country: str, active_only: bool) -> str:
    return LIB + "?" + urlencode({
        "active_status": "active" if active_only else "all",
        "ad_type": "all",
        "country": country,
        "view_all_page_id": page_id,
        "search_type": "page",
        "media_type": "all",
    })


# ---------------------------------------------------------------- normalização

def _get(d: dict, *keys, default=None):
    """Busca a primeira chave existente (aceita snake_case e camelCase)."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, "", []):
            return d[k]
    return default


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        t = _get(v, "text")
        if t:
            return str(t)
        markup = _get(v, "markup")
        if isinstance(markup, dict):
            raw = markup.get("__html", "")
            return html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return str(v)


def _date(v) -> str:
    if v in (None, ""):
        return ""
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%d")
    return str(v)[:10]


_TEMPLATE = re.compile(r"\{\{[^}]+\}\}")  # anúncios dinâmicos: {{product.name}}


def normalize_snapshot(item: dict, source: str) -> Ad | None:
    ad_id = _get(item, "ad_archive_id", "adArchiveID", "adArchiveId", "ad_id", "id")
    if not ad_id:
        return None
    snap = _get(item, "snapshot", default={}) or {}
    bodies, titles, links, images = [], [], [], []

    def add(lst, v):
        v = _text(v).strip()
        if v and not _TEMPLATE.fullmatch(v) and v not in lst:
            lst.append(v)

    add(bodies, _get(snap, "body"))
    add(titles, _get(snap, "title"))
    add(titles, _get(snap, "link_description", "linkDescription"))
    add(links, _get(snap, "link_url", "linkUrl"))
    for img in _get(snap, "images", default=[]) or []:
        add(images, _get(img, "original_image_url", "originalImageUrl", "resized_image_url", "resizedImageUrl"))
    for vid in _get(snap, "videos", default=[]) or []:
        add(images, _get(vid, "video_preview_image_url", "videoPreviewImageUrl"))
    for card in _get(snap, "cards", default=[]) or []:
        add(bodies, _get(card, "body"))
        add(titles, _get(card, "title"))
        add(links, _get(card, "link_url", "linkUrl"))
        add(images, _get(card, "original_image_url", "originalImageUrl", "resized_image_url",
                         "video_preview_image_url", "videoPreviewImageUrl"))
    # alguns scrapers achatam os campos no nível de cima
    add(bodies, _get(item, "ad_creative_body", "body"))
    add(links, _get(item, "link_url", "linkUrl"))

    platforms = _get(item, "publisher_platform", "publisherPlatform", "publisher_platforms", default=[]) or []
    if isinstance(platforms, str):
        platforms = [platforms]

    return Ad(
        ad_id=str(ad_id),
        page_name=str(_get(item, "page_name", "pageName", default=None) or _get(snap, "page_name", "pageName", default="")),
        page_id=str(_get(item, "page_id", "pageId", "pageID", default=None) or _get(snap, "page_id", "pageId", default="")),
        bodies=bodies,
        titles=titles,
        link_urls=links,
        image_urls=images,
        start_date=_date(_get(item, "start_date", "startDate", "start_date_formatted", "ad_delivery_start_time")),
        platforms=[str(p).lower() for p in platforms],
        source=source,
    )


def find_snapshots(obj) -> list[dict]:
    """Procura recursivamente objetos de anúncio dentro de um JSON qualquer."""
    found = []
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "ad_archive_id" in cur and "snapshot" in cur:
                found.append(cur)
                continue
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return found


def parse_json_lines(text: str) -> list:
    """Respostas GraphQL do Facebook às vezes vêm com vários JSONs por linha."""
    text = text.removeprefix("for (;;);")
    out = []
    for line in text.splitlines() or [text]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------- dispatch

def collect(settings, queries: list[tuple[str, str]]) -> list[Ad]:
    """queries: lista de (tipo, valor) onde tipo é 'termo' ou 'pagina'."""
    from . import apify, meta_api, playwright_scraper

    impl = {"apify": apify.collect, "meta_api": meta_api.collect, "playwright": playwright_scraper.collect}
    ads: dict[str, Ad] = {}
    for name in settings.coletores:
        fn = impl.get(name)
        if not fn:
            log.warning("Coletor desconhecido: %s", name)
            continue
        try:
            got = fn(settings, queries)
        except Exception as e:  # um coletor quebrado não derruba os outros
            log.error("Coletor %s falhou: %s", name, e)
            continue
        log.info("Coletor %s trouxe %d anúncios", name, len(got))
        for ad in got:
            ads.setdefault(ad.ad_id, ad)
    return list(ads.values())
