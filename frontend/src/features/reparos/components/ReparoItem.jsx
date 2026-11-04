import { Link } from 'react-router'
import Badge from '../../../components/ui/Badge.jsx'
import { formatarQuando } from '../../../lib/datas.js'
import { ROTULO_CAMADA } from '../camadas.js'

// Ficha de fichário com o caminho antigo e o novo, como as do caso real na landing.
function Ficha({ rotulo, className = '', children }) {
  return (
    <div className={`folha border-t-2 border-t-rec/45 p-3.5 ${className}`}>
      <p className="text-[12.5px]">{rotulo}</p>
      <p className="mt-2 text-[14.5px] font-medium break-words text-navy">{children}</p>
    </div>
  )
}

function ReparoItem({ reparo }) {
  return (
    <li className="grid gap-5 border-b border-pauta py-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-10">
      <div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h3 className="font-display text-[19px] leading-snug font-bold text-navy">
            Passo {reparo.passo}: {reparo.intencao}
          </h3>
        </div>
        <p className="mt-1.5 text-[14px]">
          <Link
            to={`/painel/tarefas/${reparo.fluxoId}`}
            className="text-navy underline decoration-ink/60 underline-offset-[3px] hover:text-ink"
          >
            {reparo.fluxoNome}
          </Link>
          , {formatarQuando(reparo.em)}
        </p>
        <p className="mt-3 max-w-[56ch] text-[15px] leading-relaxed">{reparo.explicacao}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Badge tom={reparo.camada === 4 ? 'neutro' : 'tinta'}>
            Resolvido por: {ROTULO_CAMADA[reparo.camada]}
            {reparo.parecido ? ` (${reparo.parecido}%)` : ''}
          </Badge>
          {reparo.execucaoId && (
            <Link
              to={`/painel/execucoes/${reparo.execucaoId}`}
              className="inline-flex min-h-8 items-center text-[13.5px] text-navy underline decoration-ink/60 underline-offset-[3px] hover:text-ink"
            >
              Ver a execução
            </Link>
          )}
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2.5 sm:gap-4">
        <Ficha rotulo="Caminho antigo" className="lg:-rotate-1">
          <span className="line-through decoration-rec-texto/70">{reparo.antes}</span>
        </Ficha>
        <span aria-hidden="true" className="font-hand text-[30px] font-bold text-ink">
          ›
        </span>
        <Ficha rotulo="Caminho novo" className="lg:rotate-[0.8deg]">
          {reparo.depois}
        </Ficha>
      </div>
    </li>
  )
}

export default ReparoItem
