"""Raspagem direta da página pública da Biblioteca de Anúncios (EXPERIMENTAL).

Não precisa de token, mas o Facebook muda o site com frequência e pode bloquear
acessos automatizados. Abre a busca num Chromium headless, rola a página e
captura os dados de anúncio que o próprio site carrega (respostas GraphQL +
JSON embutido no HTML).

Requer: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import json
import logging
import re

from . import find_snapshots, keyword_url, normalize_snapshot, page_url, parse_json_lines

log = logging.getLogger(__name__)

SCROLLS = 8


def collect(settings, queries):
    from playwright.sync_api import sync_playwright

    ads = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="pt-BR", viewport={"width": 1366, "height": 900})
        for kind, value in queries:
            url = keyword_url(value, settings.pais, settings.apenas_ativos) if kind == "termo" \
                else page_url(value, settings.pais, settings.apenas_ativos)
            raw: list[dict] = []
            page = ctx.new_page()

            def on_response(resp):
                if "graphql" not in resp.url:
                    return
                try:
                    for obj in parse_json_lines(resp.text()):
                        raw.extend(find_snapshots(obj))
                except Exception:
                    pass

            page.on("response", on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
                for _ in range(SCROLLS):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
                    if len(raw) >= settings.max_anuncios_por_busca:
                        break
                # primeiros resultados vêm embutidos no HTML
                for blob in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',
                                       page.content(), flags=re.S):
                    try:
                        raw.extend(find_snapshots(json.loads(blob)))
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                log.warning("Playwright falhou em %s: %s", value, e)
            finally:
                page.close()
            for it in raw[: int(settings.max_anuncios_por_busca)]:
                ad = normalize_snapshot(it, "playwright")
                if ad:
                    ads.setdefault(ad.ad_id, ad)
        browser.close()
    return list(ads.values())
