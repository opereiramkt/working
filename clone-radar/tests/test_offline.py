"""Teste ponta a ponta sem internet: sobe um servidor local com imagens/landings
falsas e roda o radar num JSON no formato do Apify.

  python tests/test_offline.py
"""
from __future__ import annotations

import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def make_creative(path: Path):
    img = Image.new("RGB", (1080, 1080), "#1e3a8a")
    d = ImageDraw.Draw(img)
    d.rectangle((80, 620, 1000, 820), fill="#ea580c")
    d.ellipse((380, 120, 700, 440), fill="#fbbf24")
    d.polygon([(100, 500), (300, 300), (500, 520)], fill="#06b6d4")
    for i in range(8):
        d.rectangle((120 + i * 110, 880, 180 + i * 110, 1000), fill="#ffffff")
    img.save(path, "JPEG", quality=92)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="radar-test-"))
    www = tmp / "www"
    (tmp / "criativos").mkdir(parents=True)
    www.mkdir()
    make_creative(tmp / "criativos" / "meu.jpg")

    # clone: mesma imagem com borda, redimensionada e recomprimida
    with Image.open(tmp / "criativos" / "meu.jpg") as im:
        ImageOps.expand(im.resize((600, 600)), border=20, fill="white").save(www / "clone.jpg", quality=55)
    # imagem sem relação
    other = Image.new("RGB", (800, 800), "#ffffff")
    ImageDraw.Draw(other).ellipse((100, 100, 700, 700), fill="#00aa00")
    other.save(www / "outro.jpg")

    own_landing = (ROOT.parent / "index.html").read_text(encoding="utf-8")
    (www / "landing-clone.html").write_text(own_landing.replace("JC Instalação Elétrica", "Mestre da Automação"),
                                            encoding="utf-8")
    (www / "landing-afiliado.html").write_text(
        "<html><body>Compre aqui <a href='https://pay.hotmart.com/X12345678Y'>comprar</a></body></html>",
        encoding="utf-8")

    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(www), **k)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    def item(i, page, body, title="", img=None, link=None):
        return {"ad_archive_id": str(1000 + i), "page_id": str(500 + i), "page_name": page,
                "start_date": 1761955200, "publisher_platform": ["FACEBOOK", "INSTAGRAM"],
                "snapshot": {"body": {"text": body}, "title": title, "link_url": link,
                             "images": [{"original_image_url": f"{base}/{img}"}] if img else []}}

    ads = [
        item(1, "Mestre da Automação",
             "O guia que transforma eletricistas comuns em integradores de automação — com tabelas "
             "de preço prontas pra você cobrar certo em 2026. 3 sistemas completos (Cabeada, Wi-Fi e "
             "Zigbee) + passo a passo de instalação. Só R$ 37,90!",
             "Apostila Automação 2026", "clone.jpg", f"{base}/landing-clone.html"),
        item(2, "Elétrica Pro",
             "Eletricista, aprenda automação residencial com Zigbee e Wi-Fi e saiba quanto cobrar. "
             "Tabela de preços inclusa + bônus Manual do Eletricista.",
             "Curso de automação", "outro.jpg"),
        item(3, "Pizzaria do Zé", "Promoção de pizza grande + refrigerante só hoje! Peça já pelo app.",
             "Pizza", "outro.jpg"),
        item(4, "Parceiro Afiliado", "Apostila Automação Residencial 2026 com tabelas de preço prontas.",
             "Apostila", "clone.jpg", f"{base}/landing-afiliado.html"),
        item(5, "JC Instalação Elétrica", "Meu próprio anúncio — deve ser ignorado.", "", "clone.jpg"),
    ]
    (tmp / "ads.json").write_text(json.dumps(ads, ensure_ascii=False), encoding="utf-8")

    cfg = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    cfg = cfg.replace("pasta_criativos: ofertas/apostila-automacao/criativos", "pasta_criativos: criativos")
    cfg = cfg.replace("landing: ../index.html", f"landing: {ROOT.parent / 'index.html'}")
    cfg = cfg.replace("ids_checkout: []", "ids_checkout: [X12345678Y]")
    (tmp / "config.yaml").write_text(cfg, encoding="utf-8")

    out = subprocess.run([sys.executable, "-m", "radar", "--config", str(tmp / "config.yaml"),
                          "run", "--sem-ia", "--sem-alerta", "--de-json", str(tmp / "ads.json")],
                         cwd=ROOT, capture_output=True, text=True)
    print(out.stdout, out.stderr)
    assert out.returncode == 0, "radar falhou"

    import sqlite3
    rows = {r[0]: r[1:] for r in sqlite3.connect(tmp / "dados" / "radar.db").execute(
        "SELECT ad_id, score, verdict FROM matches")}
    print("\nResultados:", json.dumps(rows, indent=1, ensure_ascii=False))
    assert rows["1001"][0] >= 80, "clone deveria ter score alto"
    img_score = json.loads(sqlite3.connect(tmp / "dados" / "radar.db").execute(
        "SELECT data FROM matches WHERE ad_id='1001'").fetchone()[0])["imagem"]
    print("score do criativo clonado (com moldura/redimensionado):", img_score)
    assert img_score >= 80, "criativo clonado deveria ser reconhecido"
    assert "1003" not in rows, "pizzaria não deveria ser suspeita"
    assert "1005" not in rows, "página própria deveria ser ignorada"
    assert rows.get("1004", (0, "afiliado"))[1] == "afiliado", "afiliado deveria ser reconhecido"
    report = tmp / "relatorios" / "ultimo.html"
    assert report.exists()
    keep = ROOT / "relatorios"
    keep.mkdir(exist_ok=True)
    shutil.copy(report, keep / "exemplo-teste.html")
    print("\nOK ✅  relatório de exemplo em", keep / "exemplo-teste.html")
    srv.shutdown()


if __name__ == "__main__":
    main()
