"""Alertas: Telegram, Discord/Slack (webhook) e e-mail. Configure só o que usar.

Variáveis de ambiente:
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  DISCORD_WEBHOOK_URL
  SLACK_WEBHOOK_URL
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO
"""
from __future__ import annotations

import html
import logging
import os
import smtplib
from email.message import EmailMessage

import requests

log = logging.getLogger(__name__)

LABEL = {
    "clone_direto": "🚨 CLONE DIRETO",
    "copia_parcial": "⚠️ CÓPIA PARCIAL",
    "produto_similar": "👀 PRODUTO SIMILAR",
    "afiliado": "🤝 AFILIADO",
    "sem_relacao": "✅ SEM RELAÇÃO",
}


def _lines(m) -> list[str]:
    ad = m.ad
    out = [
        f"{LABEL.get(m.verdict, m.verdict)} — score {m.score:.0f}/100",
        f"Sua oferta: {m.offer.nome}",
        f"Anunciante: {ad.page_name or '?'} (page id {ad.page_id or '?'})",
        f"No ar desde: {ad.start_date or '?'}",
        f"Sinais: copy {m.copy_score:.0f} · criativo {m.image_score:.0f} · "
        f"landing {m.landing_score:.0f} · tema {m.theme_score:.0f}",
    ]
    if m.signature_hits:
        out.append("Frases suas encontradas: " + ", ".join(m.signature_hits[:6]))
    if m.ai:
        out.append("IA: " + m.ai.get("resumo", "")[:400])
    snippet = ad.text.replace("\n", " ")[:220]
    if snippet:
        out.append(f"Texto: “{snippet}…”")
    out.append(f"Biblioteca: {ad.library_url}")
    if m.landing_url:
        out.append(f"Landing: {m.landing_url}")
    return out


def _telegram(text_html: str):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return False
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20, json={
        "chat_id": chat, "text": text_html[:4000], "parse_mode": "HTML",
        "disable_web_page_preview": True})
    if not r.ok:
        log.warning("Telegram: %s", r.text[:200])
    return r.ok


def _webhook(env: str, key: str, text: str):
    url = os.environ.get(env)
    if not url:
        return False
    r = requests.post(url, json={key: text[:1900]}, timeout=20)
    if not r.ok:
        log.warning("%s: %s", env, r.text[:200])
    return r.ok


def _email(subject: str, body: str):
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("ALERT_EMAIL_TO")
    if not (host and to):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, to
    msg["From"] = os.environ.get("SMTP_USER", to)
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT") or 587), timeout=30) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
        s.send_message(msg)
    return True


def channels() -> list[str]:
    c = []
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        c.append("telegram")
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        c.append("discord")
    if os.environ.get("SLACK_WEBHOOK_URL"):
        c.append("slack")
    if os.environ.get("SMTP_HOST") and os.environ.get("ALERT_EMAIL_TO"):
        c.append("email")
    return c


def send_text(title: str, lines: list[str]):
    plain = title + "\n\n" + "\n".join(lines)
    tg = f"<b>{html.escape(title)}</b>\n\n" + "\n".join(html.escape(l) for l in lines)
    sent = []
    for name, fn in [("telegram", lambda: _telegram(tg)),
                     ("discord", lambda: _webhook("DISCORD_WEBHOOK_URL", "content", plain)),
                     ("slack", lambda: _webhook("SLACK_WEBHOOK_URL", "text", plain)),
                     ("email", lambda: _email(title, plain))]:
        try:
            if fn():
                sent.append(name)
        except Exception as e:
            log.warning("Falha no canal %s: %s", name, e)
    return sent


def send(m):
    return send_text(f"Clone Radar · {m.offer.nome}", _lines(m))
