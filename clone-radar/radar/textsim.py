"""Similaridade de texto (copy, tema e frases-assinatura). Sem dependências."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

STOP = set("""
a o e as os um uma uns umas de do da dos das no na nos nas em por para pra pro com sem
que se ao aos à às ou mas mais menos muito muita muitos muitas ja já nao não sim seu sua
seus suas meu minha voce você voces vocês ele ela eles elas isso isto esse essa este esta
aqui ali la lá so só tambem também como quando onde porque pq ate até agora hoje todo toda
todos todas cada ser ter tem vai vou foi era sao são esta está estao estão fazer faz
the and for you your with this that are
""".split())


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _words(s: str) -> list[str]:
    return normalize(s).split()


def _ngrams(words: list[str], n: int) -> set[tuple]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _char_grams(s: str, n: int = 5) -> Counter:
    s = normalize(s)
    return Counter(s[i:i + n] for i in range(len(s) - n + 1))


def _cos(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def copy_similarity(mine: list[str], theirs: str) -> float:
    """0-100: quanto do texto deles é cópia (literal ou levemente alterada) do seu."""
    tw = _words(theirs)
    if len(tw) < 4:
        return 0.0
    t3 = _ngrams(tw, 3)
    tc = _char_grams(theirs)
    best = 0.0
    all_mine3: set[tuple] = set()
    for m in mine:
        mw = _words(m)
        m3 = _ngrams(mw, 3)
        all_mine3 |= m3
        if not m3:
            continue
        # fração da SUA copy que aparece no anúncio deles
        contain = len(m3 & t3) / len(m3)
        # semelhança de caracteres pega copy com palavras trocadas/sinônimos leves
        char = max(0.0, (_cos(_char_grams(m), tc) - 0.25) / 0.6)
        best = max(best, contain, min(1.0, char))
    # fração do anúncio DELES que veio de alguma das suas copies (mistura de trechos)
    if t3 and all_mine3:
        best = max(best, len(t3 & all_mine3) / len(t3))
    return round(100 * min(1.0, best), 1)


def _stem(w: str) -> str:
    return w[:6]


def _bag(texts: list[str]) -> Counter:
    c = Counter()
    for t in texts:
        c.update(_stem(w) for w in _words(t) if len(w) > 2 and w not in STOP and not w.isdigit())
    return c


def theme_similarity(offer_texts: list[str], theirs: str) -> float:
    """0-100: o anúncio fala do mesmo assunto/produto?"""
    cos = _cos(_bag(offer_texts), _bag([theirs]))
    return round(100 * min(1.0, cos / 0.45), 1)


def signature_hits(signatures: list[str], theirs: str) -> list[str]:
    t = f" {normalize(theirs)} "
    hits = []
    for sig in signatures:
        n = normalize(sig)
        if n and f" {n} " in t:
            hits.append(sig)
    return hits
