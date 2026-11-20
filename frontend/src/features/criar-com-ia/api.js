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

function mapearPedido(pedido) {
  return {
    id: pedido.id,
    situacao: SITUACAO[pedido.status],
    texto: pedido.prompt,
    endereco: pedido.start_url,
    nome: pedido.name,
    passos: pedido.events.filter((evento) => evento.kind === 'step').map((evento) => evento.text),
    ultimoAviso: pedido.events.findLast((evento) => evento.kind !== 'step')?.text ?? null,
    pergunta: pedido.question ? { texto: pedido.question.text, opcoes: pedido.question.options } : null,
    erro: pedido.error,
    tarefaId: pedido.flow_id,
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
