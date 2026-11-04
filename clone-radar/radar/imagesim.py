"""Similaridade visual de criativos via hash perceptual (dHash 256 bits).

Detecta o mesmo criativo mesmo redimensionado, recomprimido, espelhado ou com
pequeno corte/borda. Para vídeos, o anúncio traz a thumbnail; coloque também um
print do seu vídeo na pasta de criativos.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageOps

log = logging.getLogger(__name__)

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CloneRadar/1.0"}
_cache: dict[str, tuple[int, bytes] | None] = {}


def dhash(img: Image.Image, size: int = 16) -> int:
    g = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (left > right)
    return bits


def trim(img: Image.Image) -> Image.Image:
    """Remove bordas de cor sólida (clones costumam emoldurar o criativo)."""
    rgb = img.convert("RGB")
    area = rgb.size[0] * rgb.size[1]
    for _ in range(3):  # repete: moldura branca em volta de fundo azul, etc.
        bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
        d = ImageChops.difference(rgb, bg)
        box = ImageChops.add(d, d, 2.0, -30).getbbox()
        if not box or box == (0, 0, *rgb.size) or (box[2] - box[0]) * (box[3] - box[1]) < 0.4 * area:
            break
        # recua 2px p/ descartar a faixa borrada pela compressão JPEG
        rgb = rgb.crop((box[0] + 2, box[1] + 2, max(box[0] + 3, box[2] - 2), max(box[1] + 3, box[3] - 2)))
    return rgb


def _variants(img: Image.Image) -> list[Image.Image]:
    img = trim(img)
    w, h = img.size
    crop = img.crop((int(w * .08), int(h * .08), int(w * .92), int(h * .92)))
    return [img, ImageOps.mirror(img), crop]


def hash_folder(folder: Path | None) -> list[tuple[str, int]]:
    out = []
    if not folder or not folder.exists():
        return out
    for f in sorted(folder.rglob("*")):
        if f.suffix.lower() not in EXTS:
            continue
        try:
            with Image.open(f) as img:
                img.load()
                for v in _variants(img):
                    out.append((str(f), dhash(v)))
        except Exception as e:
            log.warning("Não consegui ler %s: %s", f, e)
    return out


def fetch(url: str) -> tuple[int, bytes] | None:
    """Baixa a imagem do anúncio e devolve (hash, bytes)."""
    if url in _cache:
        return _cache[url]
    res = None
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        data = r.content
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            res = (dhash(trim(img)), data)
    except Exception as e:
        log.debug("Falha ao baixar imagem %s: %s", url, e)
    _cache[url] = res
    return res


def similarity(h1: int, h2: int, bits: int = 256) -> float:
    return 1 - bin(h1 ^ h2).count("1") / bits


def best_match(mine: list[tuple[str, int]], urls: list[str], max_images: int = 4):
    """Retorna (score 0-100, seu_arquivo, url_anuncio, bytes_anuncio)."""
    best = (0.0, None, None, None)
    first_bytes = None
    for url in urls[:max_images]:
        got = fetch(url)
        if not got:
            continue
        h, data = got
        first_bytes = first_bytes or (url, data)
        for path, mh in mine:
            sim = similarity(h, mh)
            # 0.75 ~ imagens diferentes, >=0.93 ~ mesma imagem
            score = max(0.0, min(1.0, (sim - 0.75) / 0.18)) * 100
            if score > best[0]:
                best = (round(score, 1), path, url, data)
    if best[3] is None and first_bytes:
        best = (best[0], best[1], first_bytes[0], first_bytes[1])
    return best
