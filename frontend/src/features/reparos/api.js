import { pedir } from '../../lib/http.js'
import { ROTULO_CAMADA } from './camadas.js'

const TIPOS_DE_PEDIDO = { confirm: 'confirmar', choose: 'escolher', captcha: 'captcha', uncertain: 'incerto' }

const MAXIMO_POR_PAGINA = 100

export function mapearPedido(pedido) {
  return {
    id: pedido.id,
    tipo: TIPOS_DE_PEDIDO[pedido.kind],
    execucaoId: pedido.run_id,
    fluxoNome: pedido.flow_name,
    posicaoItem: pedido.item_position,
    titulo: pedido.title,
    texto: pedido.message,
    opcoes: pedido.options.map((opcao) => ({
      id: opcao.id,
      texto: opcao.text,
      parecido: Math.round(opcao.score * 100),
    })),
  }
}

export async function listarPedidos() {
  return (await pedir('/help-requests')).map(mapearPedido)
}

export function responderPedido(id, { acao, opcao }) {
  return pedir(`/help-requests/${id}/answer`, {
    metodo: 'POST',
    corpo: { action: acao, ...(acao === 'choose' ? { option_id: opcao } : {}) },
  })
}

export async function listarReparos() {
  const { items } = await pedir(`/repairs?limit=${MAXIMO_POR_PAGINA}`)
  return items.map((reparo) => ({
    id: reparo.id,
    fluxoId: reparo.flow_id,
    fluxoNome: reparo.flow_name,
    execucaoId: reparo.run_id,
    passo: reparo.step_position,
    intencao: reparo.intent,
    em: reparo.created_at,
    camada: reparo.layer,
    parecido: reparo.score ? Math.round(reparo.score * 100) : null,
    antes: reparo.old_path,
    depois: reparo.new_path,
    explicacao: reparo.explanation,
  }))
}

export async function obterResolvidosPorCamada() {
  const linhas = await pedir('/repairs/stats')
  // Sem nenhum passo rodado, não há o que mostrar
  if (linhas.every((linha) => linha.steps === 0)) return []
  return linhas.map((linha) => ({
    camada: linha.layer,
    rotulo: ROTULO_CAMADA[linha.layer],
    quantidade: linha.steps,
  }))
}
