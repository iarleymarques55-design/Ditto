# Ditto: extensão gravadora

Grava uma tarefa feita no navegador e envia para o Ditto, que passa a repeti-la. Também pode rodar as repetições neste Chrome, com as contas logadas nele ([executor](#executar-neste-chrome)).

## Instalar (modo de desenvolvimento)

1. No Chrome, abra `chrome://extensions`.
2. Ligue o **Modo do desenvolvedor**, no canto superior direito.
3. Clique em **Carregar sem compactação** e escolha esta pasta (`extension/`).

## Usar

1. No painel do Ditto, clique em **Gravar tarefa**, dê um nome e informe o endereço inicial.
2. Uma aba nova abre com a barra de gravação. Faça a tarefa normalmente.
3. Os dados da tela final são guardados sozinhos ao clicar em **Parar e salvar**: tabelas com cabeçalho, fichas (`th` + `td`), pares `dt`/`dd`, textos "Rótulo: valor" e campos só de leitura com rótulo. Menu, cabeçalho e rodapé do site ficam de fora, assim como campos que a pessoa ainda pode editar e rótulos que aparecem mais de uma vez. Esses dados são opcionais: se um deles não aparecer em uma execução, fica vazio e a tarefa segue. O que não servir, remova na revisão do painel.
   Para ler um valor de uma tela do meio do caminho, clique uma vez em **Capturar dados** e depois em cada dado que quiser guardar. Cada clique já fica salvo, com o nome do rótulo ao lado do dado (sem rótulo, vira "Dado 1", "Dado 2"…). Clicar no cabeçalho de uma tabela guarda a tabela inteira. **Pronto** ou Esc termina.
4. Em planilhas do **Excel Online**, digite nas células normalmente. Cada célula vira dois passos que o Ditto consegue repetir: ir até a célula pela Caixa de Nome e escrever o valor na Barra de fórmulas. As células não viram perguntas no painel.
5. Clique em **Parar e salvar**. A tarefa abre no painel, pronta para revisar.

## O que ela faz e o que não faz

- Só grava as abas iniciadas pelo painel e as janelas abertas por elas. Fora disso, nenhum script é injetado.
- O valor de campos de senha, cartão e código nunca é lido, nem enviado.
- Ignora eventos falsos criados por scripts da página.
- Recebe um token que dura 2 horas e só serve para enviar gravações. Ele não dá acesso à sua conta.
- Precisa de acesso a todos os sites (`<all_urls>`) porque a tarefa pode acontecer em qualquer portal.

## Limitações

- Envio de arquivo para o site (`input type=file`) não é gravado.
- Campos preenchidos pelo gerenciador de senhas sem nenhuma digitação podem não ser notados.
- No navegador do worker, a repetição começa sem a sua sessão. Se o site pede login, saia da conta antes de gravar, para o login entrar na gravação. Com o executor ligado, isso não é preciso: a repetição usa as contas deste Chrome.
- Código por e-mail ou SMS e login pelo Google não funcionam na repetição.
- Cliques só são reconhecidos em botões, links e elementos com a mãozinha do mouse. Confira na barra a linha "Anotado".

## Executar neste Chrome

Com o executor ligado, o worker roda as tarefas da sua conta aqui, em uma aba ao lado da que você está usando e com as contas que já estão logadas.

1. No `.env` do backend, coloque `EXTENSION_RUNNER_PORT=8765` e reinicie o worker.
2. No painel, abra a página da conta e clique em **Ligar neste Chrome**.
3. O ícone da extensão mostra se o executor está ligado.

Como funciona ([runner.js](runner.js)):

- A extensão conecta no endereço de [config.js](config.js) (`ws://127.0.0.1:8765` no seu computador) com um token próprio, que dura 30 dias e não vale em nenhuma rota da API. Fora do computador local, só aceita `wss://`.
- Cada linha abre uma aba ao lado da aba ativa, controlada com `chrome.debugger`. Só as abas abertas pelo Ditto, e as janelas que elas abrem, são controladas. Comandos para qualquer outra aba são recusados pela própria extensão.
- Enquanto uma linha roda, o Chrome mostra a faixa "começou a depurar este navegador". Clicar em **Cancelar** nela para a linha.
- Os downloads da linha passam pela sua pasta Downloads e são apagados de lá depois que o Ditto pega o arquivo. Com o worker na mesma máquina, ele copia da pasta; com o worker na nuvem ou no Docker, a extensão baixa o mesmo endereço de novo, com as suas contas, e manda o conteúdo pela conexão (até 40 MB). Download gerado por envio de formulário (POST) não pode ser buscado de novo.
- Precisa das permissões `debugger` (controlar as abas do Ditto) e `alarms` (tentar de novo quando o worker estava desligado).

## Publicar com o Ditto na nuvem

O worker publicado atende várias pessoas ao mesmo tempo, cada uma no próprio Chrome.

1. Em [config.js](config.js), troque `RELE_URL` pelo endereço do worker publicado, com `wss://` (ex.: `wss://ditto-worker.up.railway.app/extension`).
2. Em `content_scripts.matches`, no [manifest.json](manifest.json), troque `http://localhost:5173/*` pelo endereço do painel (`https://...`).
3. No worker, preencha `EXTENSION_RELAY_HOST=0.0.0.0` e `EXTENSION_ORIGINS=["chrome-extension://<id>"]` com o id da extensão (aparece em `chrome://extensions`). Sem a lista, o worker não inicia com a porta aberta para a rede.
