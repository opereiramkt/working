"""API oficial da Biblioteca de Anúncios (Graph API /ads_archive).

ATENÇÃO: fora da União Europeia a API oficial só retorna anúncios de temas
sociais/políticos. Para anúncios comerciais veiculados SÓ no Brasil ela volta
vazia — por isso o coletor padrão é o Apify. Use este se suas ofertas (ou as dos
clones) também rodam na Europa. Precisa de META_ACCESS_TOKEN de um app com a
identidade verificada em facebook.com/ads/library/api.
A API também não devolve imagens nem o link de destino, só os textos.
"""
from __future__ import annotations

import logging
import os

import requests

from ..models import Ad

log = logging.getLogger(__name__)

EU = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE",
      "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]

FIELDS = ",".join([
    "id", "page_id", "page_name", "ad_creative_bodies", "ad_creative_link_titles",
    "ad_creative_link_captions", "ad_creative_link_descriptions", "ad_delivery_start_time",
    "publisher_platforms", "ad_snapshot_url",
])


def collect(settings, queries):
    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN não definido")
    url = f"https://graph.facebook.com/{settings.meta_api_versao}/ads_archive"
    countries = [settings.pais] if settings.pais in EU else EU
    ads: list[Ad] = []
    for kind, value in queries:
        params = {
            "access_token": token,
            "ad_type": "ALL",
            "ad_active_status": "ACTIVE" if settings.apenas_ativos else "ALL",
            "ad_reached_countries": str(countries).replace("'", '"'),
            "fields": FIELDS,
            "limit": min(int(settings.max_anuncios_por_busca), 100),
        }
        if kind == "termo":
            params["search_terms"] = value
        else:
            params["search_page_ids"] = f"[{value}]"
        r = requests.get(url, params=params, timeout=60)
        if r.status_code != 200:
            log.warning("Meta API (%s=%s): %s", kind, value, r.text[:300])
            continue
        for d in r.json().get("data", []):
            ads.append(Ad(
                ad_id=str(d["id"]),
                page_name=d.get("page_name", ""),
                page_id=str(d.get("page_id", "")),
                bodies=d.get("ad_creative_bodies") or [],
                titles=(d.get("ad_creative_link_titles") or []) + (d.get("ad_creative_link_descriptions") or []),
                link_urls=[],
                image_urls=[],
                start_date=(d.get("ad_delivery_start_time") or "")[:10],
                platforms=[p.lower() for p in d.get("publisher_platforms") or []],
                source="meta_api",
            ))
    return ads
