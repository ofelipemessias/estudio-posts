# Estúdio de Posts

Gera posts pro Instagram de advogados (carrossel, post único e roteiro
de Reels), com as artes prontas em PNG 1080x1350 no visual de tweet,
dentro das regras de publicidade da OAB (Provimento 205/2021).

## Como funciona

- **Dono (você):** convida pessoas, define o prazo de acesso (7, 15, 30,
  60, 90 dias ou ilimitado), limites de posts e buscas por mês, marca
  quem é pagante, pausa, reativa, estende ou encerra o acesso. No
  **Painel do dono** vê quem está usando, quantos posts cada um gerou e
  quanto de IA cada um gastou (em US$ e R$). Também pode gerar posts
  pra qualquer perfil, escolhendo na tela **"Quem vai gerar agora?"**
  (cartões com foto, uso, voz e o quanto cada perfil está completo).
- **Convidado:** recebe um link, cria a senha, escolhe a área e
  configura o próprio nicho (temas, público, posts antigos pro "DNA").
  Se a área dele não estiver entre os modelos prontos, escolhe "Outra área",
  digita e a IA monta os temas e o público.
  Só vê o que é dele. O prazo começa a contar quando ele cria a senha.
- **Cobrança:** fora do sistema (link da Asaas). Aqui só existe a
  marcação "pagante" e as observações.

## Publicar no Instagram

No celular, o botão **"📱 Postar pelo celular"** do post copia a legenda
(com as hashtags) e abre o menu de compartilhar já com todas as artes, na
ordem do carrossel: é só escolher o Instagram, "Feed" e colar a legenda.
No computador, use "Baixar tudo (.zip)".

### Assinatura (Asaas)

Com `ASAAS_API_KEY`, `ASAAS_AMBIENTE` e `ASAAS_WEBHOOK_TOKEN` no `.env`:
no fim do teste a pessoa vê os planos e paga por **cartão** (recorrência
automática, cartão digitado na página do Asaas) ou **Pix**. O Asaas avisa o
sistema pelo webhook `https://SEU_DOMINIO/webhooks/asaas` e o acesso é
estendido sozinho. Cadastre esse webhook no painel do Asaas com a mesma senha
do `ASAAS_WEBHOOK_TOKEN` e os eventos de cobrança e de assinatura.
Comece em `ASAAS_AMBIENTE=sandbox` (sem dinheiro de verdade).

### Publicação automática (plano Completo)

Com `ZERNIO_API_KEY` no `.env` ([Zernio](https://zernio.com), cobra por
conta de Instagram conectada, as 2 primeiras grátis):

1. No **Painel do dono → Ações → "Liberar publicação automática"**, depois
   que a pessoa pagar o upgrade (a cobrança é por fora).
2. A pessoa, na aba **Perfil → "Conectar Instagram"**, entra com o login do
   Instagram. A conta precisa ser **profissional** (Empresa ou Criador).
3. Em cada post: **"Publicar agora"** ou **agendar** (horário de Brasília).
   Acompanhe tudo na aba **Agenda**.

Desligar o upgrade ou apagar o perfil desconecta a conta no Zernio (e ela
para de ser cobrada). Reels não publica automático (precisa de vídeo).

## Nome do produto

O nome que aparece na interface vem de `APP_NOME` no `.env` (padrão:
"Estúdio de Posts"). Pra trocar a marca, mude a linha e reinicie
(`docker compose up -d`, ou o compose do servidor).

## Rodar no seu computador

1. Copie `.env.example` para `.env` e preencha: `ANTHROPIC_API_KEY`,
   `SECRET_KEY`, `DONO_EMAIL` e `DONO_SENHA_INICIAL` (mín. 10 caracteres).
2. Com o Docker Desktop aberto: `docker compose up --build -d`
3. Abra http://localhost:5100 e entre com o e-mail e a senha de dono.

## Colocar online (servidor com domínio e HTTPS)

Pré-requisitos: um domínio (ex.: `app.seudominio.com.br`) com registro DNS
tipo **A** apontando pro servidor, e um proxy reverso com HTTPS. O exemplo
abaixo usa um **Caddy** que já roda em Docker no servidor.

1. No `.env`, preencha `PROXY_NETWORK` com o nome da rede Docker do seu
   Caddy (`docker network ls`).
2. No `Caddyfile` do seu Caddy, acrescente:
   ```
   app.seudominio.com.br {
   	reverse_proxy estudio-posts:5100
   }
   ```
   e recarregue o Caddy.
3. No servidor, dentro da pasta do projeto:
   ```
   cp .env.example .env && nano .env
   docker compose -f compose.yaml -f compose.servidor.yaml up --build -d
   ```

O Caddy busca o certificado HTTPS sozinho no primeiro acesso ao domínio.
Com `compose.servidor.yaml`, o cookie de login passa a trafegar só por HTTPS.

## Dia a dia

- Atualizar depois de mudar o código: repetir o `up --build -d`.
- **Backup:** a pasta `dados/` tem o banco (SQLite), fotos e artes de
  todo mundo. Copie ela com frequência.
- Ver os logs: `docker compose logs -f estudio`

## Segurança

- Senhas com hash; sessão em cookie `HttpOnly` + `SameSite=Lax` (e
  `Secure` online); bloqueio de 15 min após 6 senhas erradas; pedidos
  vindos de outros sites são recusados.
- Cada convidado só acessa o próprio perfil, posts, artes e zips.
- Links de convite e de nova senha valem 7 dias e só uma vez.

## Testes

Não chamam a IA de verdade (respostas simuladas) e usam um banco temporário:

```
pip install -r requirements.txt
python tests/teste_seguranca.py
python tests/teste_voz_e_texto.py
python tests/teste_nome_app.py
python tests/teste_perfis.py
python tests/teste_area.py
python tests/teste_publicacao.py
python tests/teste_assinatura.py
python tests/teste_precos.py
```

## Arquivos

- `app.py`: servidor, contas, convites, painel e rotas
- `motor/gerar_post.py`: prompts, regras da OAB, modelos de área, radar
- `motor/pagamentos.py`: assinaturas e cobrança (API do Asaas)
- `motor/publicador.py`: publicação e agendamento no Instagram (API do Zernio)
- `motor/render_post.py`: desenho das artes (baseado no renderizador
  MIT da skill de carrossel tweet)
- `fonts/`: Liberation Sans (SIL OFL, ver LICENSE-LiberationFonts.txt)
- `static/index.html`: interface
- `tests/`: testes automáticos
- `CHANGELOG.md`: histórico de versões
- `THIRD_PARTY_NOTICES.md`: créditos e licenças de terceiros

## Aviso

Os textos são gerados por IA e seguem as regras de publicidade da
advocacia (Provimento 205/2021 do CFOAB) como orientação, mas **a revisão
final e a responsabilidade pelo que é publicado são sempre do advogado**.
