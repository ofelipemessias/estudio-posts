# Changelog

Registro da evolução do Estúdio de Posts. Datas no formato AAAA-MM-DD.

## [0.4.0] - 2026-09-29
### Adicionado
- Nome do produto configurável pela variável **`APP_NOME`** no `.env`. Vale
  pro título da aba, a logo (tela de login, tela de convite e topo) e as
  mensagens de convite (inclusive a pronta pro WhatsApp). Trocar a marca
  passa a ser só mudar essa linha e reiniciar. Sem `APP_NOME`, continua
  "Estúdio de Posts".
- Destaque automático na logo: última palavra ("Estúdio de **Posts**") ou
  sufixo como "+" ("Advoga**+**").
- Teste `tests/teste_nome_app.py`, incluindo proteção contra nomes com
  caracteres especiais (o nome é sempre escapado, nunca vira HTML/JS).

## [0.3.0] - 2026-09-29
### Adicionado
- Campo **"Voz dos posts"** no perfil: primeira pessoa ("eu"), institucional
  ("nós") ou neutra. A IA segue a voz nos slides, na legenda e no roteiro.
- Testes automáticos em `tests/` (segurança/acesso e voz/texto), com IA simulada.
### Alterado
- Travessões (— e –) removidos também da legenda e do roteiro de Reels, não
  só dos slides.
- Regra reforçada de publicidade da OAB: a IA não insinua indenização como
  certa ("pode ser cobrado da empresa", "muito mais do que isso"); usa
  "pode, dependendo do caso, gerar direito à reparação".
- Perfis novos nascem com voz em primeira pessoa.

## [0.2.0] - 2026-09-29
### Adicionado
- Contas com login: **dono** e **convidados**.
- Convite por link (vale 7 dias), com criação de senha; o mesmo mecanismo
  serve pra redefinir senha.
- Prazo de acesso por pessoa (7, 15, 30, 60, 90 dias ou ilimitado), contado
  a partir da ativação; ações de estender, deixar sem prazo, encerrar,
  pausar e reativar.
- Limite de posts e de buscas no radar por mês, por pessoa.
- **Painel do dono**: situação de cada pessoa, posts no mês e no total,
  buscas no radar, custo estimado de IA (US$ e R$), último acesso,
  marcação de pagante e observações. Mensagem de convite pronta pro WhatsApp.
- Primeiro acesso guiado pro convidado (escolha da área e criação do perfil).
- Registro de tokens e buscas de cada chamada à IA, pra calcular o custo.
- Segurança: senhas com hash, cookie de sessão HttpOnly/SameSite (Secure
  online), bloqueio após tentativas erradas, bloqueio de requisições vindas
  de outros sites; cada convidado só acessa o que é dele.
- Configuração pra rodar atrás de um proxy reverso (Caddy) com HTTPS.

## [0.1.0] - 2026-09-28
### Adicionado
- Primeira versão, pra rodar localmente.
- **Perfis** (advogado/escritório) com identidade visual, área, temas,
  público e "DNA" de escrita; modelos prontos (Digital/Consumidor/Bancário,
  Previdenciário, Trabalhista, Família, em branco).
- Geração de carrossel, post único e roteiro de Reels, com artes em PNG
  1080x1350 no visual de tweet, legenda, hashtags e alertas de
  "conferir antes de publicar".
- Radar de pautas: notícias reais da semana (busca na web, com fonte) ou
  ideias atemporais.
- Edição do texto dos slides com redesenho na hora e download em .zip.
- Regras de publicidade da advocacia (Provimento 205/2021 do CFOAB) em
  todos os prompts.
