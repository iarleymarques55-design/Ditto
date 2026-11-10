const conteudo = document.getElementById('conteudo')

function criar(tag, propriedades = {}, texto = '') {
  const el = document.createElement(tag)
  Object.assign(el, propriedades)
  if (texto) el.textContent = texto
  return el
}

async function desenhar() {
  const estado = await chrome.runtime.sendMessage({ type: 'ditto:status' })
  conteudo.replaceChildren()

  if (!estado?.recording) {
    conteudo.append(
      criar('h1', {}, 'Nenhuma gravação agora'),
      criar('p', {}, 'Para gravar, abra o painel do Ditto e clique em "Gravar tarefa". Só as abas iniciadas por lá são gravadas.'),
    )
    return
  }

  const passos = `${estado.steps} ${estado.steps === 1 ? 'passo' : 'passos'}`
  conteudo.append(criar('h1', {}, estado.name), criar('p', {}, `Gravando, ${passos}.`))
  if (estado.error) conteudo.append(criar('p', { className: 'erro', role: 'alert' }, estado.error))

  const acoes = criar('div', { className: 'acoes' })
  const parar = criar('button', { className: 'cheio', disabled: estado.sending }, estado.sending ? 'Salvando...' : 'Parar e salvar')
  parar.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: 'ditto:stop' })
    desenhar()
  })
  const descartar = criar('button', { className: 'leve', disabled: estado.sending }, 'Descartar')
  descartar.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: 'ditto:discard' })
    desenhar()
  })
  acoes.append(parar, descartar)
  conteudo.append(acoes)
}

desenhar()
