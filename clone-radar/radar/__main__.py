"""Clone Radar — vigia a Biblioteca de Anúncios da Meta atrás de clones das suas ofertas.

Uso:
  python -m radar run                      # varredura completa
  python -m radar run --sem-ia             # sem análise por IA
  python -m radar run --de-json dados.json # analisa um export do Apify (sem coletar)
  python -m radar teste-alerta             # manda uma mensagem de teste nos canais
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import alerts, collectors, config, imagesim, landing, report, scoring
from .store import Store

log = logging.getLogger("radar")


def _ignored(ad, s) -> bool:
    if ad.page_id and ad.page_id in {str(x) for x in s.page_ids_ignorados}:
        return True
    if ad.page_name and ad.page_name.strip().lower() in {p.lower() for p in s.paginas_ignoradas}:
        return True
    doms = {d.lower().removeprefix("www.") for d in s.dominios_ignorados}
    return bool(doms) and any(landing.domain(u) in doms for u in ad.link_urls)


def run(args):
    s = config.load(args.config)
    use_ai = s.analise_ia and not args.sem_ia
    if use_ai and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.warning("ANTHROPIC_API_KEY ausente — rodando sem análise por IA")
        use_ai = False

    for o in s.ofertas:
        o.creative_hashes = imagesim.hash_folder(o.pasta_criativos)
        o.landing_text, own_ids = landing.load_own(o.landing, s.base_dir)
        o.ids_checkout = sorted(set(o.ids_checkout) | set(own_ids))
        log.info("Oferta '%s': %d copies, %d variações de criativo, landing %s",
                 o.nome, len(o.copies), len(o.creative_hashes),
                 "ok" if o.landing_text else "não carregada")

    if args.de_json:
        raw = json.loads(Path(args.de_json).read_text(encoding="utf-8"))
        ads = [a for a in (collectors.normalize_snapshot(it, "json") for it in raw) if a]
    else:
        queries = sorted({("termo", t) for o in s.ofertas for t in o.termos_busca})
        queries += [("pagina", str(p["page_id"])) for p in s.paginas_monitoradas if p.get("page_id")]
        ads = collectors.collect(s, queries)
    ads = [a for a in ads if not _ignored(a, s)]
    log.info("%d anúncios para analisar", len(ads))

    store = Store(s.base_dir / "dados" / "radar.db")
    suspects, n_new, n_alert = [], 0, 0
    for ad in ads:
        # avalia contra todas as ofertas e fica com a mais parecida
        best = None
        for o in s.ofertas:
            m = scoring.evaluate(o, ad, s, use_ai)
            if best is None or m.score > best.score:
                best = m
        if best is None or best.score < s.limite_suspeito:
            continue
        is_new, should_alert = store.record(best, s.limite_alerta)
        suspects.append(best)
        n_new += is_new
        if should_alert and not args.sem_alerta:
            sent = alerts.send(best)
            n_alert += 1
            log.info("ALERTA %s (%s, %.0f) -> %s", best.ad.page_name, best.verdict, best.score,
                     ", ".join(sent) or "nenhum canal configurado")

    suspects.sort(key=lambda m: m.score, reverse=True)
    path = report.render(suspects, store.top_pages(), s.base_dir / "relatorios",
                         {"anuncios": len(ads), "alertas": n_alert, "novos": n_new})
    log.info("Relatório: %s", path)
    print(f"\n{len(ads)} anúncios analisados · {len(suspects)} suspeitos · "
          f"{n_new} novos · {n_alert} alertas\nRelatório: {path}")


def test_alert(_args):
    ch = alerts.channels()
    if not ch:
        sys.exit("Nenhum canal configurado. Defina TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID, "
                 "DISCORD_WEBHOOK_URL, SLACK_WEBHOOK_URL ou SMTP_*.")
    sent = alerts.send_text("Clone Radar · teste", ["Se você recebeu isso, os alertas estão funcionando ✅"])
    print("Enviado para:", ", ".join(sent) or "nenhum (veja os avisos acima)")


def main():
    p = argparse.ArgumentParser(prog="radar", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="varredura completa")
    r.add_argument("--sem-ia", action="store_true", help="não usa análise por IA")
    r.add_argument("--sem-alerta", action="store_true", help="só gera o relatório")
    r.add_argument("--de-json", help="analisa um JSON exportado do Apify em vez de coletar")
    r.set_defaults(fn=run)
    t = sub.add_parser("teste-alerta", help="envia mensagem de teste")
    t.set_defaults(fn=test_alert)
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args.fn(args)


if __name__ == "__main__":
    main()
