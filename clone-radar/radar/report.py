"""Relatório HTML autocontido (abre em qualquer navegador, inclusive no celular)."""
from __future__ import annotations

import base64
import html
import io
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import imagesim

COLORS = {
    "clone_direto": "#d93025", "copia_parcial": "#e8710a", "produto_similar": "#9334e6",
    "afiliado": "#188038", "sem_relacao": "#5f6368",
}
NAMES = {
    "clone_direto": "Clone direto", "copia_parcial": "Cópia parcial",
    "produto_similar": "Produto similar", "afiliado": "Afiliado", "sem_relacao": "Sem relação",
}


def _thumb(data: bytes | None) -> str:
    if not data:
        return ""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((320, 320))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _bar(label: str, v: float) -> str:
    return (f'<div class="bar"><span>{label}</span><div><i style="width:{v:.0f}%"></i></div>'
            f'<b>{v:.0f}</b></div>')


def _card(m) -> str:
    e = html.escape
    ad = m.ad
    color = COLORS.get(m.verdict, "#5f6368")
    ad_img = ""
    if m.image_pair:
        got = imagesim.fetch(m.image_pair[1])
        ad_img = _thumb(got[1] if got else None)
    elif ad.image_urls:
        got = imagesim.fetch(ad.image_urls[0])
        ad_img = _thumb(got[1] if got else None)
    own_img = ""
    if m.image_pair and m.image_score >= 40:
        try:
            own_img = _thumb(Path(m.image_pair[0]).read_bytes())
        except OSError:
            pass
    imgs = ""
    if own_img:
        imgs += f'<figure><img src="{own_img}" alt=""><figcaption>Seu criativo</figcaption></figure>'
    if ad_img:
        imgs += f'<figure><img src="{ad_img}" alt=""><figcaption>Criativo deles</figcaption></figure>'
    ai = ""
    if m.ai:
        items = "".join(f"<li>{e(x)}</li>" for x in m.ai.get("elementos_copiados", [])[:8])
        ai = f'<div class="ai"><b>Análise da IA:</b> {e(m.ai.get("resumo", ""))}<ul>{items}</ul></div>'
    sigs = "".join(f'<span class="chip">{e(s)}</span>' for s in m.signature_hits)
    links = f'<a href="{e(ad.library_url)}" target="_blank" rel="noopener">Ver na Biblioteca</a>'
    if m.landing_url:
        links += f' · <a href="{e(m.landing_url)}" target="_blank" rel="noopener">Landing deles</a>'
    return f"""
<article class="card" style="--c:{color}">
  <header>
    <span class="tag">{NAMES.get(m.verdict, m.verdict)}</span>
    <span class="score">{m.score:.0f}</span>
  </header>
  <h3>{e(ad.page_name or 'Anunciante desconhecido')}</h3>
  <p class="meta">Oferta: {e(m.offer.nome)} · desde {e(ad.start_date or '?')} ·
     {e(', '.join(ad.platforms) or '')} · page id {e(ad.page_id or '?')}</p>
  <div class="grid">
    <div>
      {_bar('Copy', m.copy_score)}{_bar('Criativo', m.image_score)}
      {_bar('Landing', m.landing_score)}{_bar('Tema', m.theme_score)}
      <div class="chips">{sigs}</div>
    </div>
    <div class="imgs">{imgs}</div>
  </div>
  {ai}
  <details><summary>Texto do anúncio</summary><pre>{e(ad.text[:3000])}</pre></details>
  <p class="links">{links}</p>
</article>"""


def render(matches, top_pages, out_dir: Path, stats: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    cards = "\n".join(_card(m) for m in matches) or \
        '<p class="empty">Nenhum suspeito acima do limite nesta varredura. 🎉</p>'
    rows = "".join(
        f"<tr><td>{html.escape(p or '?')}</td><td>{html.escape(pid or '')}</td>"
        f"<td>{n}</td><td>{s:.0f}</td></tr>" for p, pid, n, s in top_pages)
    doc = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clone Radar</title>
<style>
:root {{ --bg:#f6f7f9; --fg:#1f2328; --muted:#5f6368; --card:#fff; --line:#e3e6ea; --track:#eceff3; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#0f1115; --fg:#e8eaed; --muted:#9aa0a6; --card:#181b21; --line:#2a2f37; --track:#2a2f37; }} }}
:root[data-theme="dark"] {{ --bg:#0f1115; --fg:#e8eaed; --muted:#9aa0a6; --card:#181b21; --line:#2a2f37; --track:#2a2f37; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif }}
main {{ max-width:980px; margin:0 auto; padding:24px 16px 64px }}
h1 {{ margin:0 0 4px; font-size:26px }} .sub {{ color:var(--muted); margin:0 0 20px }}
.stats {{ display:flex; flex-wrap:wrap; gap:12px; margin-bottom:24px }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 14px; min-width:130px }}
.stat b {{ display:block; font-size:22px }} .stat span {{ color:var(--muted); font-size:13px }}
.card {{ background:var(--card); border:1px solid var(--line); border-left:5px solid var(--c); border-radius:12px; padding:16px; margin-bottom:16px }}
.card header {{ display:flex; justify-content:space-between; align-items:center }}
.tag {{ background:var(--c); color:#fff; font-weight:600; font-size:12px; padding:3px 10px; border-radius:99px; text-transform:uppercase; letter-spacing:.03em }}
.score {{ font-size:28px; font-weight:700; color:var(--c) }}
h3 {{ margin:8px 0 2px }} .meta {{ color:var(--muted); font-size:13px; margin:0 0 12px }}
.grid {{ display:grid; grid-template-columns:1fr auto; gap:16px }}
@media (max-width:640px) {{ .grid {{ grid-template-columns:1fr }} }}
.bar {{ display:grid; grid-template-columns:70px 1fr 32px; align-items:center; gap:8px; font-size:13px; margin:4px 0 }}
.bar div {{ background:var(--track); border-radius:99px; height:8px; overflow:hidden }}
.bar i {{ display:block; height:100%; background:var(--c) }} .bar b {{ text-align:right }}
.chips {{ margin-top:8px }} .chip {{ display:inline-block; border:1px solid var(--c); color:var(--c); border-radius:99px; padding:1px 8px; font-size:12px; margin:2px 4px 2px 0 }}
.imgs {{ display:flex; gap:8px; flex-wrap:wrap }} figure {{ margin:0; text-align:center }}
figure img {{ width:150px; height:150px; object-fit:cover; border-radius:8px; border:1px solid var(--line) }}
figcaption {{ font-size:12px; color:var(--muted) }}
.ai {{ margin-top:12px; padding:10px 12px; background:var(--track); border-radius:8px; font-size:14px }}
.ai ul {{ margin:6px 0 0; padding-left:18px }}
details {{ margin-top:10px }} pre {{ white-space:pre-wrap; font:13px/1.45 inherit; color:var(--muted) }}
a {{ color:inherit }} .links {{ margin:10px 0 0; font-size:14px }}
table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden }}
td,th {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; font-size:14px }}
.empty {{ color:var(--muted) }}
</style></head><body><main>
<h1>Clone Radar</h1>
<p class="sub">Varredura de {now:%d/%m/%Y %H:%M} na Biblioteca de Anúncios da Meta</p>
<div class="stats">
  <div class="stat"><b>{stats.get('anuncios', 0)}</b><span>anúncios analisados</span></div>
  <div class="stat"><b>{len(matches)}</b><span>suspeitos</span></div>
  <div class="stat"><b>{stats.get('alertas', 0)}</b><span>alertas novos</span></div>
  <div class="stat"><b>{stats.get('novos', 0)}</b><span>suspeitos novos</span></div>
</div>
{cards}
<h2>Anunciantes mais suspeitos (histórico)</h2>
<table><tr><th>Página</th><th>Page ID</th><th>Anúncios</th><th>Maior score</th></tr>{rows}</table>
</main></body></html>"""
    path = out_dir / f"radar-{now:%Y%m%d-%H%M}.html"
    path.write_text(doc, encoding="utf-8")
    (out_dir / "ultimo.html").write_text(doc, encoding="utf-8")
    return path
