"""Combina os sinais num score 0-100 por (oferta, anúncio)."""
from __future__ import annotations

import logging

from . import imagesim, landing, textsim
from .models import Ad, Match, Offer

log = logging.getLogger(__name__)


def heuristic(m: Match) -> float:
    evidence = max(m.copy_score, m.image_score, m.landing_score)
    sig = min(36, 12 * len(m.signature_hits))
    return round(min(100.0, evidence * 0.7 + m.theme_score * 0.3 + sig), 1)


def evaluate(offer: Offer, ad: Ad, settings, use_ai: bool) -> Match:
    m = Match(offer=offer, ad=ad)
    text = ad.text
    m.copy_score = textsim.copy_similarity(offer.copies, text) if offer.copies else 0.0
    m.theme_score = textsim.theme_similarity(
        [*offer.copies, offer.produto, offer.nome, *offer.termos_busca], text)
    m.signature_hits = textsim.signature_hits(offer.assinaturas, text)

    ad_bytes, own_img = None, None
    if ad.image_urls:
        score, own_img, url, ad_bytes = imagesim.best_match(offer.creative_hashes, ad.image_urls)
        m.image_score = score
        if own_img and score > 0:
            m.image_pair = (own_img, url)

    # pré-filtro: só gasta rede/IA com quem tem algum sinal
    pre = heuristic(m)
    promising = pre >= 25 or m.theme_score >= 45 or m.image_score >= 50

    their_text = ""
    if promising and settings.analisar_landing and ad.link_urls:
        final_url, their_text, ids = landing.fetch(ad.link_urls[0])
        m.landing_url = final_url or landing.unwrap(ad.link_urls[0])
        if their_text and offer.landing_text:
            m.landing_score = textsim.copy_similarity([offer.landing_text], their_text)
            m.signature_hits = sorted(set(m.signature_hits) |
                                      set(textsim.signature_hits(offer.assinaturas, their_text)))
        if offer.ids_checkout and set(ids) & set(offer.ids_checkout):
            m.affiliate = True

    m.score = heuristic(m)

    if use_ai and promising and not m.affiliate and m.score >= settings.limite_suspeito - 20:
        from . import ai_judge
        if not own_img and offer.creative_hashes:
            own_img = offer.creative_hashes[0][0]
        m.ai = ai_judge.judge(m, ad_bytes, own_img, their_text)
        if m.ai:
            if m.ai["veredito"] == "afiliado":
                m.affiliate = True
            elif m.ai["veredito"] == "sem_relacao":
                m.score = round(min(m.score, m.ai["score"]), 1) if m.score < 70 else m.score
            else:
                m.score = round(max(m.score, 0.4 * m.score + 0.6 * m.ai["score"]), 1)
    return m
