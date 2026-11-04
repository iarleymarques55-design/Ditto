import { MATRIZ, PASSO_EXPORTAR, PASSOS } from './demoRoteiro.js'

const folha = 'rounded-[2px] border border-line bg-papel-folha shadow-papel'

function Passo({ numero, texto, estado, reparado }) {
  const ativo = estado === 'ativo'
  return (
    <li
      aria-current={ativo ? 'step' : undefined}
      className={`flex items-baseline gap-2 border-t border-dashed border-tinta-media px-1.5 py-[5px] ${ativo ? 'bg-tinta-clara' : ''}`}
    >
      <span className="w-3 shrink-0 text-[11.5px] text-tinta-media tabular-nums">{numero}</span>
      <div className="min-w-0 flex-1">
        <p>{texto}</p>
        {reparado && (
          <div className="mt-1 mb-0.5 flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <span className="text-[11.5px]">{MATRIZ.caminhoReparado}</span>
            <span className="inline-block -rotate-3 rounded-[2px] border-[1.5px] border-ink px-1.5 py-px font-sans text-[10.5px] font-medium motion-safe:animate-carimbar">
              {MATRIZ.carimbo}
            </span>
          </div>
        )}
      </div>
      {estado === 'feito' && (
        <span className="shrink-0 text-[11px]">
          ✓<span className="sr-only"> concluído</span>
        </span>
      )}
    </li>
  )
}

// A matriz do mimeógrafo: a gravação de onde saem as cópias.
function MatrizGravada({ passoAtual, concluidos, reparado, className = '' }) {
  return (
    <div className={`relative ${className}`}>
      <div aria-hidden="true" className={`absolute inset-0 translate-x-[10px] translate-y-[9px] lg:rotate-[2.5deg] ${folha}`} />
      <div aria-hidden="true" className={`absolute inset-0 translate-x-[5px] translate-y-[4px] lg:rotate-[1.2deg] ${folha}`} />

      <div className={`relative px-3.5 pt-3.5 pb-3 font-display text-[12.5px] text-ink [text-shadow:0_0_1px_rgba(102,82,173,.45)] ${folha}`}>
        <p className="text-[11px]">{MATRIZ.cabecalho}</p>
        <p className="mt-1 text-[16px] leading-snug font-bold">{MATRIZ.titulo}</p>
        <ol className="mt-2.5">
          {PASSOS.map((texto, indice) => {
            const numero = indice + 1
            const estado = numero === passoAtual ? 'ativo' : numero <= concluidos ? 'feito' : 'pendente'
            return (
              <Passo
                key={texto}
                numero={numero}
                texto={texto}
                estado={estado}
                reparado={reparado && numero === PASSO_EXPORTAR}
              />
            )
          })}
        </ol>
      </div>
    </div>
  )
}

export default MatrizGravada
