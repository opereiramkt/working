"""Baixa a página de destino do anúncio e compara com a sua página de vendas."""
from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# IDs de produto em checkouts comuns no Brasil
CHECKOUT_PATTERNS = [
    r"pay\.hotmart\.com/([A-Z0-9]{6,})",
    r"go\.hotmart\.com/([A-Z0-9]{6,})",
    r"pay\.kiwify\.com\.br/([A-Za-z0-9]{5,})",
    r"(?:sun|chk)\.eduzz\.com/(\d{4,})",
    r"app\.monetizze\.com\.br/checkout/([A-Za-z0-9]{5,})",
    r"checkout\.perfectpay\.com\.br/pay/([A-Za-z0-9]{5,})",
    r"pay\.cakto\.com\.br/([A-Za-z0-9_]{5,})",
    r"ticto\.app/([A-Za-z0-9]{5,})",
]

_cache: dict[str, tuple[str, str, list[str]]] = {}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
    except Exception:
        pass
    return "\n".join(p.parts)


def checkout_ids(html: str) -> list[str]:
    ids = []
    for pat in CHECKOUT_PATTERNS:
        ids += re.findall(pat, html)
    return sorted(set(ids))


def unwrap(url: str) -> str:
    """Remove o redirecionador l.facebook.com/l.php?u=..."""
    u = urlparse(url)
    if u.netloc.endswith("facebook.com") and u.path.startswith("/l.php"):
        return parse_qs(u.query).get("u", [url])[0]
    return url


def domain(url: str) -> str:
    return urlparse(unwrap(url)).netloc.lower().removeprefix("www.")


def fetch(url: str) -> tuple[str, str, list[str]]:
    """Retorna (url_final, texto_visível, ids_de_checkout)."""
    url = unwrap(url)
    if url in _cache:
        return _cache[url]
    res = ("", "", [])
    try:
        r = requests.get(url, headers=UA, timeout=25, allow_redirects=True)
        if r.ok and "html" in r.headers.get("content-type", "html"):
            res = (r.url, html_to_text(r.text), checkout_ids(r.text))
    except Exception as e:
        log.debug("Falha ao abrir landing %s: %s", url, e)
    _cache[url] = res
    return res


def load_own(ref: str | None, base_dir: Path) -> tuple[str, list[str]]:
    """Sua landing: caminho local (relativo ao config) ou URL."""
    if not ref:
        return "", []
    if ref.startswith("http"):
        _, text, ids = fetch(ref)
        return text, ids
    p = (base_dir / ref).resolve()
    if not p.exists():
        log.warning("Landing %s não encontrada", p)
        return "", []
    html = p.read_text(encoding="utf-8", errors="ignore")
    return html_to_text(html), checkout_ids(html)
