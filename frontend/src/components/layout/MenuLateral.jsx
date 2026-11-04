import { NavLink } from 'react-router'

const ABAS = [
  { rotulo: 'Mesa', para: '/painel', exato: true },
  { rotulo: 'Tarefas', para: '/painel/tarefas' },
  { rotulo: 'Execuções', para: '/painel/execucoes' },
  { rotulo: 'Reparos', para: '/painel/reparos', comContagem: true },
]

// Abas de divisória de fichário: saem da borda direita da folha no desktop e do topo no celular.
// A aba ativa tem a cor da folha e encosta nela, como se a folha fosse a continuação dela.
function MenuLateral({ pedidosPendentes = 0, className = '' }) {
  return (
    <nav aria-label="Painel" className={className}>
      <ul className="flex gap-1 lg:flex-col lg:gap-1.5">
        {ABAS.map(({ rotulo, para, exato, comContagem }) => (
          <li key={para} className="min-w-0 flex-1 lg:flex-none">
            <NavLink
              to={para}
              end={exato}
              className={({ isActive }) =>
                `relative flex min-h-12 items-center justify-center gap-1 rounded-t-[6px] px-1 font-display text-[13.5px] font-bold text-navy sm:gap-1.5 sm:px-1.5 sm:text-[16px] lg:justify-start lg:rounded-t-none lg:rounded-r-[6px] lg:px-3.5 ${
                  isActive
                    ? 'z-10 -mb-px bg-papel-folha lg:mb-0 lg:-ml-px lg:shadow-[6px_4px_10px_-6px_rgba(70,48,20,0.45)]'
                    : 'bg-post-it shadow-[inset_0_-3px_4px_-3px_rgba(70,48,20,0.3)] hover:bg-tinta-clara lg:shadow-[inset_4px_0_5px_-4px_rgba(70,48,20,0.4),3px_3px_6px_-4px_rgba(70,48,20,0.4)]'
                }`
              }
            >
              {rotulo}
              {comContagem && pedidosPendentes > 0 && (
                <span className="absolute -top-1.5 right-0 inline-flex size-[18px] shrink-0 items-center justify-center rounded-full bg-rec-texto font-sans text-[12px] font-bold text-white sm:static sm:size-[22px]">
                  {pedidosPendentes}
                  <span className="sr-only"> pedidos esperando você</span>
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

export default MenuLateral
