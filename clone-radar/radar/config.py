"""Carrega config.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import Offer


@dataclass
class Settings:
    base_dir: Path
    pais: str = "BR"
    max_anuncios_por_busca: int = 60
    apenas_ativos: bool = True
    coletores: list[str] = field(default_factory=lambda: ["apify"])
    apify_actor: str = "curious_coder~facebook-ads-library-scraper"
    meta_api_versao: str = "v23.0"
    limite_suspeito: float = 45
    limite_alerta: float = 65
    analise_ia: bool = True
    analisar_landing: bool = True
    paginas_ignoradas: list[str] = field(default_factory=list)
    page_ids_ignorados: list[str] = field(default_factory=list)
    dominios_ignorados: list[str] = field(default_factory=list)
    paginas_monitoradas: list[dict] = field(default_factory=list)
    ofertas: list[Offer] = field(default_factory=list)


def load(path: str | Path) -> Settings:
    path = Path(path).resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = path.parent
    g = raw.get("geral", {}) or {}
    s = Settings(base_dir=base)
    for key in Settings.__dataclass_fields__:
        if key in g:
            setattr(s, key, g[key])
    s.paginas_monitoradas = raw.get("paginas_monitoradas") or []

    for o in raw.get("ofertas") or []:
        pasta = o.get("pasta_criativos")
        s.ofertas.append(Offer(
            id=str(o["id"]),
            nome=o.get("nome", o["id"]),
            produto=(o.get("produto") or "").strip(),
            termos_busca=o.get("termos_busca") or [],
            copies=[c.strip() for c in (o.get("copies") or []) if c and c.strip()],
            assinaturas=o.get("assinaturas") or [],
            pasta_criativos=(base / pasta) if pasta else None,
            landing=o.get("landing"),
            ids_checkout=[str(x) for x in (o.get("ids_checkout") or [])],
        ))
    if not s.ofertas:
        raise SystemExit("Nenhuma oferta configurada em 'ofertas:' no config.yaml")
    return s
