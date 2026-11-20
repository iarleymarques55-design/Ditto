import { Link } from 'react-router'
import { usePedidosAbertos } from '../hooks/usePedidoIa.js'

const TEXTO = {
  'na-fila': 'Na fila',
  trabalhando: 'A IA está montando',
  esperando: 'A IA está esperando você',
}

// Quem fechou a tela de acompanhamento volta por aqui
function PedidosAbertos() {
  const { dados: pedidos } = usePedidosAbertos()
  if (!pedidos?.length) return null

  return (
    <ul className="mb-6 space-y-2">
      {pedidos.map((pedido) => (
        <li key={pedido.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[15px] text-navy">
          <span className={pedido.situacao === 'esperando' ? 'font-medium text-ink' : 'text-grafite'}>{TEXTO[pedido.situacao]}:</span>
          <Link
            to={`/painel/tarefas/ia/${pedido.id}`}
            className="min-w-0 truncate underline decoration-ink/60 underline-offset-[3px] hover:text-ink max-sm:max-w-full"
          >
            {pedido.nome ?? pedido.texto}
          </Link>
        </li>
      ))}
    </ul>
  )
}

export default PedidosAbertos
