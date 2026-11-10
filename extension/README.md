# Ditto: extensão gravadora

Grava uma tarefa feita no navegador e envia para o Ditto, que passa a repeti-la.

## Instalar (modo de desenvolvimento)

1. No Chrome, abra `chrome://extensions`.
2. Ligue o **Modo do desenvolvedor**, no canto superior direito.
3. Clique em **Carregar sem compactação** e escolha esta pasta (`extension/`).

## Usar

1. No painel do Ditto, clique em **Gravar tarefa**, dê um nome e informe o endereço inicial.
2. Uma aba nova abre com a barra de gravação. Faça a tarefa normalmente.
3. Para ler um valor da tela, clique em **Capturar dado**, depois no dado, e dê um nome a ele.
4. Clique em **Parar e salvar**. A tarefa abre no painel, pronta para revisar.

## O que ela faz e o que não faz

- Só grava as abas iniciadas pelo painel e as janelas abertas por elas. Fora disso, nenhum script é injetado.
- O valor de campos de senha, cartão e código nunca é lido, nem enviado.
- Ignora eventos falsos criados por scripts da página.
- Recebe um token que dura 2 horas e só serve para enviar gravações. Ele não dá acesso à sua conta.
- Precisa de acesso a todos os sites (`<all_urls>`) porque a tarefa pode acontecer em qualquer portal.

## Limitações

- Envio de arquivo para o site (`input type=file`) não é gravado.
- Campos preenchidos pelo gerenciador de senhas sem nenhuma digitação podem não ser notados.
- A repetição começa sem a sua sessão. Se o site pede login, saia da conta antes de gravar, para o login entrar na gravação.
- Código por e-mail ou SMS e login pelo Google não funcionam na repetição.
- Cliques só são reconhecidos em botões, links e elementos com a mãozinha do mouse. Confira na barra a linha "Anotado".

## Publicar para outro endereço do painel

As origens do painel ficam em `content_scripts.matches`, no [manifest.json](manifest.json). Em produção, troque `http://localhost:5173/*` pelo endereço real (`https://...`).
