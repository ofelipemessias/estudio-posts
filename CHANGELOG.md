# Changelog

Registro da evolução do Estúdio de Posts. Datas no formato AAAA-MM-DD.

## [0.10.4] - 2026-10-01
### Corrigido
- "O campo postalCode é inválido": com o cadastro marcado como completo, o
  sistema usava o endereço salvo no Asaas, que podia estar incompleto. Agora,
  no pagamento com cartão, a tela **sempre mostra os dados de cobrança**
  (CPF/CNPJ, celular e endereço), **já preenchidos** com o que estiver salvo,
  e o sistema confere tudo (inclusive o CEP no ViaCEP) antes de abrir o
  checkout.

## [0.10.3] - 2026-10-01
### Corrigido
- O checkout com cartão também exigia a **cidade** do cliente ("O campo city
  deve existir para o customer informado"). Agora o checkout leva os dados
  completos do pagador em `customerData`, inclusive o **código IBGE da cidade**
  (vindo do ViaCEP), como a documentação do Asaas Checkout descreve.
- Como o checkout cria o cliente do lado do Asaas, o webhook associa um
  cliente ainda desconhecido à pessoa pelo **e-mail** (consultando o cadastro
  no Asaas), só pra quem iniciou um pagamento pelo sistema.

## [0.10.2] - 2026-10-01
### Corrigido
- O checkout com cartão do Asaas também exige **endereço** no cadastro do
  cliente ("O campo address deve existir para o customer informado"). A tela
  de assinatura pede **CEP e número**; rua, bairro e cidade vêm sozinhos pelo
  ViaCEP (editáveis, pra CEPs gerais de cidade). Cadastros antigos incompletos
  são completados automaticamente no Asaas.
- Nova rota `GET /api/cep/<cep>`.

## [0.10.1] - 2026-10-01
### Corrigido
- O checkout com cartão do Asaas exige telefone no cadastro do cliente
  ("O campo phone deve existir para o customer informado"). A tela de
  assinatura agora pede o **celular com DDD** (uma vez só) e envia ao Asaas;
  clientes já cadastrados sem telefone são atualizados automaticamente.
- `.env.example`: aviso pra colocar a chave do Asaas (que começa com `$`)
  entre aspas simples, senão o Docker apaga a chave.

## [0.10.0] - 2026-10-01
### Adicionado
- **Assinatura pelo Asaas** (`motor/pagamentos.py`, só biblioteca padrão):
  - Planos **Essencial** e **Completo**, com preços no `.env`
    (`PRECO_ESSENCIAL`, `PRECO_COMPLETO`) e os limites reais do plano.
  - **Cartão de crédito em destaque** (Asaas Checkout recorrente: o cartão é
    digitado na página do Asaas e as mensalidades são automáticas) ou **Pix**
    (assinatura mensal com cobrança Pix).
  - Fim do teste: a pessoa ainda entra, mas só vê a tela de assinatura
    (perfis e posts ficam guardados). Faixa "Seu teste termina em X dias"
    nos últimos 7 dias.
  - **Webhook** `/webhooks/asaas` com senha (`ASAAS_WEBHOOK_TOKEN`, header
    `asaas-access-token`) e proteção contra avisos repetidos. Pagamento
    confirmado estende o acesso por 1 mês + tolerância (`DIAS_TOLERANCIA`),
    marca como pagante e liga/desliga a publicação automática conforme o
    plano. Atraso marca "atrasada" sem cortar na hora; estorno encerra o
    acesso; trocar de plano cancela a assinatura anterior.
  - Tela **"Minha assinatura"**: plano, situação, trocar de plano e cancelar
    (o acesso vale até o fim do período pago).
  - Painel do dono mostra plano e atraso.
- Teste `tests/teste_assinatura.py`.
### Alterado
- Sem o Asaas configurado, tudo funciona como antes (convites manuais).

## [0.9.0] - 2026-09-30
### Adicionado
- **Publicação e agendamento automáticos no Instagram** (plano "Completo"),
  pela API do Zernio (`motor/publicador.py`, só biblioteca padrão).
  - Painel do dono: **"Liberar publicação automática (Completo)"** por
    pessoa, com a etiqueta "Completo". O dono sempre pode. Desligar o
    upgrade desconecta os Instagrams da pessoa (pra parar de pagar por eles).
  - Aba Perfil: **"Conectar Instagram"** (login do próprio Instagram numa
    página segura; conta profissional, sem precisar de Página do Facebook).
    O retorno é conferido direto na API antes de salvar a conta.
  - No post: **"Publicar agora"** ou **agendar** com data e hora (horário de
    Brasília, de 5 minutos a 6 meses à frente). As artes sobem direto pro
    armazenamento do Zernio por link temporário (nunca ficam públicas no
    servidor). Reels continua manual (precisa de vídeo).
  - Nova aba **Agenda**: agendados, publicados (com link), erros e cancelar.
  - Quem não tem o upgrade vê os recursos com cadeado ("plano Completo").
  - Apagar um perfil desconecta o Instagram dele.
- Variável `ZERNIO_API_KEY` (em branco = recurso desligado).
- Teste `tests/teste_publicacao.py`.

## [0.8.0] - 2026-09-30
### Adicionado
- Botão **"📱 Postar pelo celular"** no post: copia a legenda com as
  hashtags e abre o menu de compartilhar do celular já com todas as artes
  (na ordem do carrossel), pra mandar direto pro Instagram. As artes são
  carregadas assim que o post abre, porque o celular só permite abrir o menu
  de compartilhar logo após o toque. No computador, o botão explica como
  fazer pelo celular.

## [0.7.1] - 2026-09-30
### Corrigido
- Links de convite e de nova senha saíam com `http://` quando o app roda
  atrás do Caddy (funcionavam pelo redirecionamento, mas o certo é
  `https://`). Novo `CONFIAR_PROXY=1` (já ligado no `compose.servidor.yaml`)
  faz o app confiar nos cabeçalhos do proxy.

## [0.7.0] - 2026-09-30
### Adicionado
- **Tema claro e escuro** da interface, com botão de lua/sol no topo (ao
  lado do "Sair") e nas telas de login e convite. A escolha fica salva no
  navegador; na primeira visita, segue o tema do sistema operacional. O tema
  é aplicado antes da página aparecer (sem "piscar" branco).
- Todas as cores da interface viraram variáveis (`--campo`, `--suave`,
  `--topo`...), com uma versão escura em `html.escuro`.
### Observação
- O tema muda só a aparência do sistema. As artes dos posts continuam
  seguindo o estilo escolhido em cada perfil.

## [0.6.0] - 2026-09-30
### Adicionado
- Novos modelos prontos de área: **Tributário, Empresarial, Criminal,
  Imobiliário e Saúde/Plano de Saúde** (além de Digital/Consumidor/Bancário,
  Previdenciário, Trabalhista e Família).
- **"Outra área (a IA monta pra você)"**: a pessoa digita qualquer área
  (ex.: Direito Agrário) e a IA cria os temas e o público na hora de criar o
  perfil. Se a IA falhar, o perfil é criado mesmo assim, com um aviso.
- Botão **"✨ Sugerir temas e público com IA"** na aba Perfil: preenche o
  formulário pra pessoa revisar antes de salvar (não salva sozinho).
  Limite mensal por convidado em `LIMITE_SUGESTAO_AREA_MES` (padrão 10); o
  custo entra no painel do dono.
- Teste `tests/teste_area.py`.
### Alterado
- Perfis novos nascem com o estilo **Claro (fundo branco)**. Perfis já
  existentes não mudam.
- Na janela de novo perfil, "Começar a partir do modelo" virou
  "Sua área de atuação".

## [0.5.0] - 2026-09-30
### Adicionado
- Tela **"Quem vai gerar agora?"** (estilo seleção de perfis de streaming) pro
  dono: um cartão por perfil com foto (ou iniciais nas cores da marca do
  perfil), faixa com as duas cores da marca, @, área, voz, último post,
  posts no mês e no total, e barra de "perfil completo" com o que falta
  configurar (foto, @, área, sobre, público, DNA).
- Perfis de clientes separados em "Perfis de clientes", com a situação do
  acesso (ativo, convite enviado, expirado, pausado).
- Busca por nome, @, área ou cliente, e cartão "+ Novo perfil".
- No topo, o seletor virou um botão com a foto e o nome do perfil em uso;
  clicar volta pra tela de perfis. Ao entrar com mais de um perfil, o dono
  começa pela tela de perfis.
- Rota `GET /api/perfis/<id>/avatar` (só o dono ou o próprio cliente).
- Teste `tests/teste_perfis.py`.
### Corrigido
- A etiqueta vermelha de situação (ex.: "Erro" na lista de posts) ficava
  invisível por herdar o estilo escondido das caixas de erro.

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
