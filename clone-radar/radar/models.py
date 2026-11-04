"""Estruturas de dados compartilhadas."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Offer:
    id: str
    nome: str
    produto: str = ""
    termos_busca: list[str] = field(default_factory=list)
    copies: list[str] = field(default_factory=list)
    assinaturas: list[str] = field(default_factory=list)
    pasta_criativos: Path | None = None
    landing: str | None = None
    ids_checkout: list[str] = field(default_factory=list)
    # preenchidos em tempo de execução
    landing_text: str = ""
    creative_hashes: list[tuple[str, int]] = field(default_factory=list)  # (arquivo, dhash)


@dataclass
class Ad:
    """Anúncio normalizado, independente da fonte de coleta."""
    ad_id: str
    page_name: str = ""
    page_id: str = ""
    bodies: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    link_urls: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    start_date: str = ""
    platforms: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def library_url(self) -> str:
        return f"https://www.facebook.com/ads/library/?id={self.ad_id}"

    @property
    def text(self) -> str:
        return "\n".join(dict.fromkeys([*self.titles, *self.bodies]))


@dataclass
class Match:
    offer: Offer
    ad: Ad
    copy_score: float = 0.0        # 0-100 copy literal (n-gramas)
    theme_score: float = 0.0       # 0-100 mesmo assunto (palavras)
    signature_hits: list[str] = field(default_factory=list)
    image_score: float = 0.0       # 0-100 criativo visualmente igual
    image_pair: tuple[str, str] | None = None  # (seu arquivo, url do anúncio)
    landing_score: float = 0.0     # 0-100 página de vendas parecida
    landing_url: str = ""
    affiliate: bool = False        # landing aponta pro SEU checkout
    ai: dict | None = None         # veredito da IA
    score: float = 0.0             # nota final 0-100

    @property
    def verdict(self) -> str:
        if self.affiliate:
            return "afiliado"
        if self.ai and self.ai.get("veredito"):
            return self.ai["veredito"]
        if self.score >= 80:
            return "clone_direto"
        if self.score >= 60:
            return "copia_parcial"
        return "produto_similar"
