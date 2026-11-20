import { useConsulta } from '../../../lib/useConsulta.js'
import { SITUACOES_ABERTAS, listarPedidos, obterPedido } from '../api.js'

const INTERVALO_MS = 1200
const INTERVALO_LISTA_MS = 4000

// Enquanto a IA trabalha, a tela consulta de novo a cada pouco; depois para
export function usePedidoIa(id) {
  return useConsulta(() => obterPedido(id), [id], {
    intervalo: (pedido) => (!pedido || SITUACOES_ABERTAS.includes(pedido.situacao) ? INTERVALO_MS : null),
  })
}

export function usePedidosAbertos() {
  return useConsulta(async () => (await listarPedidos()).filter((pedido) => SITUACOES_ABERTAS.includes(pedido.situacao)), [], {
    intervalo: (pedidos) => (pedidos?.length ? INTERVALO_LISTA_MS : null),
  })
}
