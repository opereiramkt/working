"""Histórico em SQLite: evita alertar o mesmo anúncio toda vez."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    ad_id TEXT, offer_id TEXT, page_name TEXT, page_id TEXT,
    score REAL, verdict TEXT, alerted_score REAL DEFAULT 0,
    first_seen TEXT, last_seen TEXT, data TEXT,
    PRIMARY KEY (ad_id, offer_id)
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def record(self, m, alert_threshold: float) -> tuple[bool, bool]:
        """Salva o match. Retorna (é_novo, deve_alertar)."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        row = self.db.execute("SELECT alerted_score FROM matches WHERE ad_id=? AND offer_id=?",
                              (m.ad.ad_id, m.offer.id)).fetchone()
        is_new = row is None
        alerted = row[0] if row else 0
        # alerta se passou do limite e (nunca alertou, ou o score subiu bastante)
        should = (m.score >= alert_threshold and not m.affiliate
                  and (alerted == 0 or m.score >= alerted + 10))
        data = json.dumps({
            "texto": m.ad.text[:2000], "links": m.ad.link_urls, "imagens": m.ad.image_urls[:4],
            "copy": m.copy_score, "tema": m.theme_score, "imagem": m.image_score,
            "landing": m.landing_score, "assinaturas": m.signature_hits, "ia": m.ai,
        }, ensure_ascii=False)
        if is_new:
            self.db.execute(
                "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?)",
                (m.ad.ad_id, m.offer.id, m.ad.page_name, m.ad.page_id, m.score, m.verdict,
                 m.score if should else 0, now, now, data))
        else:
            self.db.execute(
                "UPDATE matches SET score=?, verdict=?, last_seen=?, data=?, "
                "alerted_score=CASE WHEN ? THEN ? ELSE alerted_score END "
                "WHERE ad_id=? AND offer_id=?",
                (m.score, m.verdict, now, data, should, m.score, m.ad.ad_id, m.offer.id))
        self.db.commit()
        return is_new, should

    def top_pages(self, limit: int = 10):
        return self.db.execute(
            "SELECT page_name, page_id, COUNT(*), MAX(score) FROM matches "
            "WHERE verdict NOT IN ('afiliado','sem_relacao') GROUP BY page_id "
            "ORDER BY MAX(score) DESC, COUNT(*) DESC LIMIT ?", (limit,)).fetchall()
