import PedidoAjuda from './PedidoAjuda.jsx'

function ListaPedidos({ pedidos, aoResponder }) {
  return (
    <ul className="grid items-start gap-7 pt-3 md:grid-cols-2 xl:grid-cols-3">
      {pedidos.map((pedido, indice) => (
        <PedidoAjuda key={pedido.id} pedido={pedido} indice={indice} aoResponder={aoResponder} />
      ))}
    </ul>
  )
}

export default ListaPedidos
