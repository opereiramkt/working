"""Raspagem direta da página pública da Biblioteca de Anúncios (EXPERIMENTAL).

Não precisa de token, mas o Facebook muda o site com frequência e pode bloquear
acessos automatizados. Abre a busca num Chromium headless, rola a página e
captura os dados de anúncio que o próprio site carrega (respostas GraphQL +
JSON embutido no HTML).

Quando uma busca volta vazia, o coletor diz o motivo provável (tela de login,
captcha/checkpoint, bloqueio de rede ou layout novo) e salva print + HTML em
`relatorios/debug/` para inspeção.

Requer: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from . import find_snapshots, keyword_url, normalize_snapshot, page_url, parse_json_lines

log = logging.getLogger(__name__)

SCROLLS = 8
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")


def diagnose(page_url_now: str, html: str, n_graphql: int) -> str:
    """Classifica por que uma busca voltou vazia."""
    u = page_url_now.lower()
    h = html.lower()
    if "/checkpoint" in u or "captcha" in h or "g-recaptcha" in h or "security check" in h:
        return "captcha/checkpoint"
    if "/login" in u or 'id="login_form"' in h or 'name="login"' in h and "ads/library" not in u:
        return "tela de login"
    if "nenhum anúncio corresponde" in h or "no ads match" in h or "0 resultados" in h:
        return "busca sem resultados (página carregou normalmente)"
    if n_graphql == 0 and "ad_archive_id" not in h:
        return "layout novo (nenhuma resposta GraphQL nem JSON de anúncio)"
    return "layout novo (dados chegaram, mas em formato não reconhecido)"


def _slug(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", v.lower()).strip("-")[:40] or "busca"


def collect(settings, queries):
    from playwright.sync_api import sync_playwright

    debug_dir = Path(settings.base_dir) / "relatorios" / "debug"
    ads = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="pt-BR", user_agent=UA,
                                  viewport={"width": 1366, "height": 900})
        for kind, value in queries:
            url = keyword_url(value, settings.pais, settings.apenas_ativos) if kind == "termo" \
                else page_url(value, settings.pais, settings.apenas_ativos)
            raw: list[dict] = []
            stats = {"graphql": 0}
            page = ctx.new_page()

            def on_response(resp):
                if "graphql" not in resp.url:
                    return
                stats["graphql"] += 1
                try:
                    for obj in parse_json_lines(resp.text()):
                        raw.extend(find_snapshots(obj))
                except Exception:
                    pass

            page.on("response", on_response)
            html = ""
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
                for _ in range(SCROLLS):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
                    if len(raw) >= settings.max_anuncios_por_busca:
                        break
                html = page.content()
                # primeiros resultados vêm embutidos no HTML
                for blob in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',
                                       html, flags=re.S):
                    try:
                        raw.extend(find_snapshots(json.loads(blob)))
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                msg = str(e)
                motivo = "bloqueio de rede/proxy" if "ERR_TUNNEL" in msg or "ERR_PROXY" in msg else "erro"
                log.warning("Playwright falhou em '%s' (%s): %s", value, motivo, msg.splitlines()[0])
            else:
                if not raw:
                    motivo = diagnose(page.url, html, stats["graphql"])
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    base = debug_dir / _slug(value)
                    try:
                        page.screenshot(path=str(base.with_suffix(".png")), full_page=False)
                    except Exception:
                        pass
                    base.with_suffix(".html").write_text(html, encoding="utf-8")
                    log.warning("Playwright: 0 anúncios em '%s' — %s (debug em %s.*)", value, motivo, base)
            finally:
                page.close()
            n_before = len(ads)
            for it in raw[: int(settings.max_anuncios_por_busca)]:
                ad = normalize_snapshot(it, "playwright")
                if ad:
                    ads.setdefault(ad.ad_id, ad)
            log.info("Playwright: '%s' -> %d anúncios", value, len(ads) - n_before)
        browser.close()
    return list(ads.values())
