// Onde esta extensão procura o worker do Ditto para rodar as tarefas neste Chrome.
// No seu computador fica como está. Para publicar o Ditto, troque pelo endereço do worker
// publicado, que precisa começar com wss://, e ponha o endereço do painel em "matches" no
// manifest.json (veja "Publicar com o Ditto na nuvem" no README).
const RELE_URL = 'ws://127.0.0.1:8765/extension'

// Endereços da API para onde a gravação pode ser enviada. A página do painel informa o
// endereço, mas a extensão só aceita um desta lista ou um da mesma origem do painel: uma página
// que se passasse pelo painel não consegue mandar a gravação para outro servidor.
const API_URLS = ['http://localhost:8000/api/v1']
