import { formatarDiaCurto } from '../../../lib/datas.js'
import PassoItem from './PassoItem.jsx'

const folha = 'rounded-[2px] border border-line bg-papel-folha shadow-papel'

// A matriz do mimeógrafo em tamanho real, com as folhas de baixo aparecendo.
function ListaPassos({ fluxo, aoMudar }) {
  return (
    <div className="relative">
      <div aria-hidden="true" className={`absolute inset-0 translate-x-[9px] translate-y-[8px] rotate-[0.8deg] ${folha}`} />
      <div aria-hidden="true" className={`absolute inset-0 translate-x-[4px] translate-y-[4px] rotate-[0.3deg] ${folha}`} />
      <div className={`relative px-4 pt-5 pb-3 font-display text-ink [text-shadow:0_0_1px_rgba(102,82,173,.45)] sm:px-6 ${folha}`}>
        <p className="text-[14px]">Matriz gravada em {formatarDiaCurto(fluxo.gravadaEm)}</p>
        <ol className="mt-3">
          {fluxo.passos.map((passo) => (
            <PassoItem key={passo.id} fluxoId={fluxo.id} passo={passo} aoMudar={aoMudar} />
          ))}
        </ol>
      </div>
    </div>
  )
}

export default ListaPassos
