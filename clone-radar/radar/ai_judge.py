"""Julgamento por IA (Claude): é clone, cópia parcial, produto parecido ou nada?

Só roda nos anúncios que já passaram no pré-filtro, para economizar.
Precisa de ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"

SYSTEM = """Você é um analista de inteligência competitiva de marketing digital no Brasil.
Seu trabalho é proteger o dono de uma oferta (infoproduto/produto) detectando quem está
CLONANDO a oferta dele em anúncios da Biblioteca de Anúncios da Meta.

Classifique o anúncio suspeito em UMA categoria:
- clone_direto: copiou a oferta quase inteira (copy, criativo e/ou página praticamente iguais,
  mesmo produto, mesma promessa, mesmos bônus/preços).
- copia_parcial: reaproveitou partes reconhecíveis (trechos de copy, estrutura do criativo,
  headline, nomes de bônus, promessa específica), mesmo trocando o resto.
- produto_similar: produto/ideia muito parecida e mesmo público, mas sem copiar material.
- afiliado: parece estar vendendo o MESMO produto do dono (revenda/afiliação), não um concorrente.
- sem_relacao: só compartilha o nicho ou palavras genéricas.

Seja rigoroso: termos genéricos do nicho NÃO são cópia. Aponte evidências concretas.
score = 0 a 100, a probabilidade/gravidade de ser clone da oferta do dono."""

SCHEMA = {
    "type": "object",
    "properties": {
        "veredito": {"type": "string",
                     "enum": ["clone_direto", "copia_parcial", "produto_similar", "afiliado", "sem_relacao"]},
        "score": {"type": "integer"},
        "resumo": {"type": "string"},
        "elementos_copiados": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["veredito", "score", "resumo", "elementos_copiados"],
    "additionalProperties": False,
}

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def _img_block(data: bytes) -> dict | None:
    """Redimensiona p/ no máx. 1024px e converte em JPEG base64."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((1024, 1024))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(buf.getvalue()).decode()}}
    except Exception:
        return None


def judge(match, ad_image: bytes | None, own_image_path: str | None,
          landing_text: str = "") -> dict | None:
    import anthropic

    offer, ad = match.offer, match.ad
    content: list[dict] = []
    own_img = None
    if own_image_path:
        try:
            own_img = _img_block(Path(own_image_path).read_bytes())
        except OSError:
            pass
    if own_img:
        content += [{"type": "text", "text": "IMAGEM 1 — criativo do DONO:"}, own_img]
    ad_img = _img_block(ad_image) if ad_image else None
    if ad_img:
        content += [{"type": "text", "text": "IMAGEM 2 — criativo do anúncio SUSPEITO:"}, ad_img]

    copies = "\n---\n".join(offer.copies) or "(não informadas)"
    content.append({"type": "text", "text": f"""## OFERTA DO DONO
Nome: {offer.nome}
Produto: {offer.produto or '(não informado)'}
Frases-assinatura: {', '.join(offer.assinaturas) or '(nenhuma)'}
Copies do dono:
{copies}

Trecho da página de vendas do dono:
{offer.landing_text[:3000] or '(não disponível)'}

## ANÚNCIO SUSPEITO
Página/anunciante: {ad.page_name} (id {ad.page_id})
Início da veiculação: {ad.start_date or '?'}
Texto do anúncio:
{ad.text[:4000] or '(sem texto)'}

Link de destino: {match.landing_url or ', '.join(ad.link_urls) or '(desconhecido)'}
Trecho da página de destino do suspeito:
{landing_text[:3000] or '(não disponível)'}

## SINAIS AUTOMÁTICOS (heurísticos, podem errar)
copy literal: {match.copy_score}/100 · mesmo tema: {match.theme_score}/100 ·
criativo igual: {match.image_score}/100 · landing parecida: {match.landing_score}/100 ·
frases-assinatura encontradas: {', '.join(match.signature_hits) or 'nenhuma'}

Classifique o anúncio suspeito."""})

    try:
        resp = _get_client().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            # se o modelo recusar por política, a API refaz com o fallback recomendado
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError:
        log.warning("IA: limite de requisições atingido, pulando anúncio %s", ad.ad_id)
        return None
    except anthropic.APIStatusError as e:
        log.warning("IA: erro %s da API (%s)", e.status_code, e.message)
        return None
    except anthropic.APIConnectionError:
        log.warning("IA: falha de conexão")
        return None

    if resp.stop_reason == "refusal":
        log.info("IA recusou analisar o anúncio %s", ad.ad_id)
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("IA devolveu JSON inválido para %s", ad.ad_id)
        return None
    data["score"] = max(0, min(100, int(data.get("score", 0))))
    return data
