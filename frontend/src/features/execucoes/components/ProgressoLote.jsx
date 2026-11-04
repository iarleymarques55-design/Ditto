import { X } from 'lucide-react'
import { SITUACOES_ITEM } from '../situacoes.js'

const FOLHA = 'relative block h-[34px] w-[26px] rounded-[1px]'

// O estado aparece na forma da folha, não só na cor: impressa, marcada, em branco, riscada.
function Copia({ situacao }) {
  switch (situacao) {
    case 'ok':
      return <span className={`${FOLHA} copia-impressa bg-ink motion-safe:animate-carimbar`} />
    case 'reparado':
      return (
        <span className={`${FOLHA} copia-impressa bg-ink motion-safe:animate-carimbar`}>
          <span className="absolute -top-1 -right-1 size-3 rounded-full border-2 border-papel-folha bg-sinal" />
        </span>
      )
    case 'rodando':
      return <span className={`${FOLHA} border-[1.5px] border-ink bg-tinta-clara motion-safe:animate-pulse`} />
    case 'espera':
      return (
        <span className={`${FOLHA} flex items-center justify-center border-[1.5px] border-navy bg-post-it font-hand text-[20px] leading-none font-bold text-navy`}>
          ?
        </span>
      )
    case 'falhou':
      return (
        <span className={`${FOLHA} flex items-center justify-center border-[1.5px] border-rec-texto bg-papel-folha text-rec-texto`}>
          <X size={16} strokeWidth={3} />
        </span>
      )
    case 'pulado':
      return <span className={`${FOLHA} border border-grafite/60 bg-[linear-gradient(to_top_right,transparent_47%,var(--color-grafite)_47%,var(--color-grafite)_53%,transparent_53%)]`} />
    default:
      return <span className={`${FOLHA} border border-dashed border-tinta-media`} />
  }
}

const ORDEM_LEGENDA = ['ok', 'reparado', 'rodando', 'espera', 'falhou', 'pulado', 'pendente']

// A folha de cópias: cada linha da planilha é uma folhinha que sai da máquina.
// Com `aoSelecionar`, cada folha vira um botão que abre os detalhes daquela linha.
function ProgressoLote({ itens, selecionado, aoSelecionar }) {
  const presentes = ORDEM_LEGENDA.filter((situacao) => itens.some((item) => item.situacao === situacao))

  return (
    <div>
      <ul className="flex flex-wrap gap-x-1.5 gap-y-2" aria-label={aoSelecionar ? 'Cópias desta execução' : undefined} aria-hidden={aoSelecionar ? undefined : 'true'}>
        {itens.map((item) => {
          const descricao = `${item.rotulo}: ${SITUACOES_ITEM[item.situacao].toLowerCase()}`
          return (
            <li key={item.id}>
              {aoSelecionar ? (
                <button
                  type="button"
                  title={descricao}
                  aria-label={descricao}
                  aria-pressed={selecionado === item.id}
                  onClick={() => aoSelecionar(item.id)}
                  className={`block rounded-[2px] p-[3px] hover:bg-tinta-clara ${selecionado === item.id ? 'bg-tinta-clara outline-2 outline-ink' : ''}`}
                >
                  <Copia key={item.situacao} situacao={item.situacao} />
                </button>
              ) : (
                <span title={descricao} className="block p-[3px]">
                  <Copia key={item.situacao} situacao={item.situacao} />
                </span>
              )}
            </li>
          )
        })}
      </ul>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
        {presentes.map((situacao) => (
          <li key={situacao} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block origin-left scale-[0.6] -mr-2.5">
              <Copia situacao={situacao} />
            </span>
            {SITUACOES_ITEM[situacao]}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default ProgressoLote
