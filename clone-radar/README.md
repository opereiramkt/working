# Clone Radar 🛰️

Vigia a **Biblioteca de Anúncios da Meta** e te avisa quando alguém está clonando a sua oferta.

Para cada anúncio encontrado, o radar compara com as suas ofertas em 4 frentes:

| Sinal | Como detecta |
|---|---|
| **Copy** | Trechos da sua copy reaproveitados, literais ou com poucas palavras trocadas (n-gramas de palavras e de caracteres) |
| **Criativo** | Mesma imagem mesmo redimensionada, recomprimida, espelhada ou com borda/corte (hash perceptual). Em vídeo, usa a thumbnail |
| **Landing** | Abre a página de destino do anúncio e compara com a sua página de vendas |
| **Ideia/produto** | Mesmo assunto, mesmas frases-assinatura (nome de bônus, preço, promessa) e, por fim, **análise por IA (Claude)** olhando texto + criativo + landing |

Cada suspeito ganha um **score de 0 a 100** e um veredito:
🚨 `clone_direto` · ⚠️ `copia_parcial` · 👀 `produto_similar` · 🤝 `afiliado` (vende o SEU produto, pelo seu checkout) · ✅ `sem_relacao`.

Você recebe **alerta no Telegram** (ou Discord/Slack/e-mail) só dos **novos** suspeitos, e um **relatório HTML** com todos lado a lado (seu criativo × o deles, link pra Biblioteca e pra landing).

---

## 1. Configurar suas ofertas

Edite `config.example.yaml` (ou copie para `config.yaml`). Já está preenchido com a **Apostila Automação Residencial 2026**. Para cada oferta:

- `termos_busca`: o que o radar pesquisa na Biblioteca (pense no que um clone escreveria)
- `copies`: cole os textos dos seus anúncios
- `assinaturas`: frases que **só a sua oferta tem** (nomes de bônus, preços, promessas específicas). Pesam muito
- `pasta_criativos`: coloque suas imagens em `ofertas/<oferta>/criativos/` (para vídeo, um print do frame principal)
- `landing`: sua página de vendas (arquivo local ou URL)
- `ids_checkout`: ID do produto na Hotmart/Kiwify/Eduzz, para reconhecer **afiliados** e não confundir com clone
- `paginas_ignoradas`: suas páginas e as de parceiros
- `paginas_monitoradas`: concorrentes que você já desconfia (o radar varre todos os anúncios deles)

## 2. Chaves de acesso

| Variável | Para quê | Onde pegar |
|---|---|---|
| `APIFY_TOKEN` | **Coleta dos anúncios** (obrigatória no modo padrão) | apify.com → Settings → Integrations. Usa o actor `curious_coder/facebook-ads-library-scraper` (pago por uso, centavos por busca) |
| `ANTHROPIC_API_KEY` | Análise por IA dos suspeitos (opcional, recomendada) | console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Alertas no Telegram | Crie o bot com o @BotFather; mande uma mensagem pra ele e pegue o chat id em `https://api.telegram.org/bot<TOKEN>/getUpdates` |
| `DISCORD_WEBHOOK_URL` / `SLACK_WEBHOOK_URL` | Alertas alternativos | Configurações do canal → Integrações → Webhook |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO` | Alerta por e-mail | Seu provedor (Gmail: senha de app) |
| `META_ACCESS_TOKEN` | API oficial da Meta (opcional, veja abaixo) | facebook.com/ads/library/api |

> **Por que Apify e não a API oficial?** A API oficial da Biblioteca de Anúncios só devolve anúncios **comerciais** veiculados na **União Europeia** (fora isso, só anúncios políticos). Para ofertas rodando só no Brasil ela volta vazia. Também não traz imagens nem o link de destino. Deixei os dois coletores; ative `meta_api` em `coletores:` se você também anuncia na Europa. Existe ainda o coletor `playwright` (raspagem direta, grátis, **experimental**: o Facebook muda o site e pode bloquear).

## 3. Rodar

### Automático, a cada 6 horas (GitHub Actions) — recomendado
1. No GitHub: **Settings → Secrets and variables → Actions → New repository secret** e cadastre `APIFY_TOKEN`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
2. Aba **Actions → Clone Radar → Run workflow** para rodar a primeira vez.
3. Os alertas chegam no Telegram; o relatório fica em cada execução, em **Artifacts → relatorio-clone-radar**.

Para mudar a frequência, edite o `cron` em `.github/workflows/clone-radar.yml`.

### No seu computador
```bash
cd clone-radar
pip install -r requirements.txt
export APIFY_TOKEN=... ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
python -m radar --config config.example.yaml teste-alerta    # testa o Telegram
python -m radar --config config.example.yaml run             # varredura
```
Abra `relatorios/ultimo.html` no navegador.

Outras opções:
- `run --sem-ia` (não usa Claude) · `run --sem-alerta` (só relatório)
- `run --de-json export.json` analisa um dataset exportado do Apify sem coletar de novo
- `python tests/test_offline.py` roda um teste completo sem internet

## 4. Ajuste fino

- `limite_suspeito` (padrão 45): a partir daqui entra no relatório
- `limite_alerta` (padrão 65): a partir daqui manda alerta
- Muito alarme falso? Tire termos genéricos de `termos_busca`, aumente os limites e coloque assinaturas mais específicas.
- Deixando passar clone? Adicione mais copies e criativos (todas as variações que você roda) e termos que o clone usaria.

O histórico fica em `dados/radar.db` (SQLite): um anúncio só é alertado de novo se o score subir 10 pontos ou mais.

## Custos aproximados
- **Apify**: cobra por resultado; com 5 termos × 60 anúncios a cada 6h, fica em poucos dólares por mês. Veja o preço atual do actor.
- **Claude**: só roda nos suspeitos que passam do pré-filtro (normalmente poucos por varredura), centavos por análise.
- **GitHub Actions**: grátis dentro da cota do plano.

## Estrutura
```
radar/
  collectors/   apify.py · meta_api.py · playwright_scraper.py
  textsim.py    copy, tema e frases-assinatura
  imagesim.py   hash perceptual dos criativos
  landing.py    baixa a landing, compara e acha ID de checkout
  ai_judge.py   veredito do Claude
  scoring.py    junta tudo num score
  store.py      histórico SQLite
  alerts.py     Telegram / Discord / Slack / e-mail
  report.py     relatório HTML
```
