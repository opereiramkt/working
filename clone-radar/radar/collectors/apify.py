"""Coleta via Apify (actor de scraping da Biblioteca de Anúncios).

Precisa da variável APIFY_TOKEN. O actor padrão é configurável em
`geral.apify_actor`; enviamos os campos de entrada dos dois actors mais usados
(`curious_coder/facebook-ads-library-scraper` e `apify/facebook-ads-scraper`).
"""
from __future__ import annotations

import logging
import os

import requests

from . import keyword_url, normalize_snapshot, page_url

log = logging.getLogger(__name__)


def collect(settings, queries):
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN não definido")

    urls = []
    for kind, value in queries:
        if kind == "termo":
            urls.append(keyword_url(value, settings.pais, settings.apenas_ativos))
        else:
            urls.append(page_url(value, settings.pais, settings.apenas_ativos))

    n = int(settings.max_anuncios_por_busca)
    payload = {
        # curious_coder/facebook-ads-library-scraper
        "urls": [{"url": u} for u in urls],
        "count": n * len(urls),
        "limitPerSource": n,
        "scrapeAdDetails": False,
        # apify/facebook-ads-scraper
        "startUrls": [{"url": u} for u in urls],
        "resultsLimit": n,
    }
    endpoint = f"https://api.apify.com/v2/acts/{settings.apify_actor}/run-sync-get-dataset-items"
    log.info("Apify: %d buscas no actor %s", len(urls), settings.apify_actor)
    r = requests.post(endpoint, params={"token": token, "timeout": 600}, json=payload, timeout=660)
    r.raise_for_status()
    items = r.json()
    ads = []
    for it in items if isinstance(items, list) else []:
        ad = normalize_snapshot(it, "apify")
        if ad:
            ads.append(ad)
    return ads
