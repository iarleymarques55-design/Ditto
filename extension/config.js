// Onde esta extensão procura o worker do Ditto para rodar as tarefas neste Chrome.
// No seu computador fica como está. Para publicar o Ditto, troque pelo endereço do worker
// publicado, que precisa começar com wss://, e ponha o endereço do painel em "matches" no
// manifest.json.
const RELE_URL = 'ws://127.0.0.1:8765/extension'
