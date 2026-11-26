import { pedir } from '../../lib/http.js'

const SITUACAO = {
  queued: 'na-fila',
  running: 'trabalhando',
  waiting_answer: 'esperando',
  done: 'pronta',
  failed: 'falhou',
  canceled: 'cancelada',
}

export const SITUACOES_ABERTAS = ['na-fila', 'trabalhando', 'esperando']

const PREFIXO_RESPOSTA = 'Você respondeu: '

// Passos e dúvidas na ordem em que aconteceram; a resposta fica junto da pergunta
function montarLinhas(eventos) {
  const linhas = []
  let numero = 0
  for (const evento of eventos) {
    if (evento.kind === 'step') {
      numero += 1
      linhas.push({ tipo: 'passo', texto: evento.text, numero })
    } else if (evento.kind === 'question') {
      linhas.push({ tipo: 'pergunta', texto: evento.text, resposta: null })
    } else if (evento.kind === 'info' && evento.text.startsWith(PREFIXO_RESPOSTA)) {
      const pergunta = linhas.findLast((linha) => linha.tipo === 'pergunta')
      if (pergunta) pergunta.resposta = evento.text.slice(PREFIXO_RESPOSTA.length)
    }
  }
  return linhas
}

function mapearPedido(pedido) {
  const linhas = montarLinhas(pedido.events)
  return {
    id: pedido.id,
    situacao: SITUACAO[pedido.status],
    texto: pedido.prompt,
    endereco: pedido.start_url,
    nome: pedido.name,
    linhas,
    totalPassos: linhas.filter((linha) => linha.tipo === 'passo').length,
    totalRespostas: linhas.filter((linha) => linha.resposta !== null && linha.tipo === 'pergunta').length,
    pergunta: pedido.question ? { texto: pedido.question.text, opcoes: pedido.question.options } : null,
    erro: pedido.error,
    tarefaId: pedido.flow_id,
    // false: nenhum Chrome ligado a esta conta, e o pedido não vai sair da fila
    chromeLigado: pedido.runner_connected,
  }
}

export async function pedirParaIa({ texto, endereco, nome }) {
  const corpo = { prompt: texto, start_url: endereco }
  if (nome) corpo.name = nome
  return mapearPedido(await pedir('/ai-drafts', { metodo: 'POST', corpo }))
}

export async function obterPedido(id) {
  return mapearPedido(await pedir(`/ai-drafts/${id}`))
}

export async function listarPedidos() {
  return (await pedir('/ai-drafts')).map(mapearPedido)
}

export function responderIa(id, resposta) {
  return pedir(`/ai-drafts/${id}/answer`, { metodo: 'POST', corpo: { answer: resposta } })
}

export function cancelarPedido(id) {
  return pedir(`/ai-drafts/${id}/cancel`, { metodo: 'POST' })
}
