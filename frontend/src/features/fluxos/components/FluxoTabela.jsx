import { CalendarClock, CalendarOff } from 'lucide-react'
import { Link } from 'react-router'
import Badge from '../../../components/ui/Badge.jsx'
import Botao from '../../../components/ui/Botao.jsx'
import { formatarQuando } from '../../../lib/datas.js'
import { StatusExecucao } from '../../execucoes/index.js'

const folhaDaPilha = 'absolute inset-0 rounded-[1px] border border-[rgb(70_48_20/0.15)] bg-papel-folha shadow-[1px_1px_2px_rgba(70,48,20,0.2)]'

// A matriz em miniatura: uma pilha de folhas com o número de passos em tinta de mimeógrafo.
function PilhaMatriz({ passos }) {
  return (
    <span aria-hidden="true" className="relative block h-[72px] w-[58px] shrink-0">
      <span className={`${folhaDaPilha} translate-x-[5px] translate-y-[4px] rotate-[2.5deg]`} />
      <span className={`${folhaDaPilha} translate-x-[2px] translate-y-[2px] rotate-[1deg]`} />
      <span className={`${folhaDaPilha} flex flex-col items-center justify-center font-display text-ink [text-shadow:0_0_1px_rgba(102,82,173,.45)]`}>
        <span className="text-[25px] leading-none font-bold">{passos}</span>
        <span className="mt-0.5 text-[12px]">{passos === 1 ? 'passo' : 'passos'}</span>
      </span>
    </span>
  )
}

function Agenda({ agenda }) {
  if (!agenda) return <p className="text-[14px]">Sem agenda</p>
  const Icone = agenda.ativa ? CalendarClock : CalendarOff
  return (
    <p className="flex items-start gap-1.5 text-[14px]">
      <Icone aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-ink" />
      <span>
        {agenda.texto}
        {!agenda.ativa && ' (pausada)'}
      </span>
    </p>
  )
}

const ordemDeAtencao = { revisao: 0, analisando: 1 }

// O fichário de tarefas. A ordem é a de quem precisa de atenção: revisão primeiro.
function FluxoTabela({ fluxos }) {
  const ordenados = [...fluxos].sort((a, b) => (ordemDeAtencao[a.situacao] ?? 2) - (ordemDeAtencao[b.situacao] ?? 2))

  return (
    <ul className="border-t-[1.5px] border-navy/40">
      {ordenados.map((fluxo) => {
        const emRevisao = fluxo.situacao === 'revisao'
        const analisando = fluxo.situacao === 'analisando'
        const ultima = fluxo.ultimaExecucao
        const destino = `/painel/tarefas/${fluxo.id}`

        return (
          <li
            key={fluxo.id}
            className="grid grid-cols-[66px_minmax(0,1fr)] items-center gap-x-4 gap-y-3 border-b border-pauta py-5 md:grid-cols-[66px_minmax(0,1.3fr)_minmax(0,1fr)_auto] md:gap-x-6"
          >
            <PilhaMatriz passos={fluxo.passosTotal} />

            <div className="min-w-0">
              <h2 className="font-display text-[20px] leading-snug font-bold break-words text-navy">
                <Link to={destino} className="underline decoration-transparent underline-offset-4 hover:text-ink hover:decoration-ink">
                  {fluxo.nome}
                </Link>
              </h2>
              <p className="mt-0.5 text-[14px] break-all">{fluxo.portal}</p>
            </div>

            <div className="col-span-2 min-w-0 space-y-1.5 md:col-span-1">
              <Agenda agenda={fluxo.agenda} />
              {emRevisao && <Badge tom="perigo">Esperando sua revisão</Badge>}
              {analisando && <Badge tom="tinta">Lendo a gravação</Badge>}
              {!emRevisao && !analisando && ultima && (
                <div className="flex flex-wrap items-center gap-2 text-[14px]">
                  <span>Última: {formatarQuando(ultima.inicio)}</span>
                  <StatusExecucao situacao={ultima.situacao} />
                </div>
              )}
              {!emRevisao && !analisando && !ultima && <p className="text-[14px]">Ainda não rodou</p>}
            </div>

            <div className="col-span-2 md:col-span-1">
              {emRevisao && <Botao para={destino}>Revisar</Botao>}
              {fluxo.situacao === 'ativa' && (
                <Botao variante="contorno" para={`/painel/execucoes/nova?tarefa=${fluxo.id}`}>
                  Rodar
                </Botao>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export default FluxoTabela
