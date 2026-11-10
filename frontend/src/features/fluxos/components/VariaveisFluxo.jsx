import { useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import { responderVariavel } from '../api.js'

// Bilhete com a pergunta do Ditto, como o da seção "Como funciona" da landing.
function Bilhete({ fluxoId, variavel, aoMudar }) {
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function responder(muda) {
    setEnviando(true)
    setErro(null)
    try {
      await responderVariavel(fluxoId, variavel.id, muda)
      aoMudar()
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <li className="post-it px-4 pt-3.5 pb-3.5 even:rotate-[0.8deg] odd:-rotate-[0.8deg]">
      <p className="font-display text-[16px] leading-snug text-navy italic">"{variavel.exemplo}" muda a cada vez?</p>
      <p className="mt-1 text-[14px] leading-snug">
        Se mudar, vira <strong className="font-medium text-ink">{variavel.nome}</strong> ({variavel.origem}).
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Botao className="!px-4" disabled={enviando} onClick={() => responder(true)}>
          Muda
        </Botao>
        <Botao variante="contorno" className="!px-4" disabled={enviando} onClick={() => responder(false)}>
          Fica igual
        </Botao>
      </div>
      {erro && (
        <p role="alert" className="mt-2 text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </li>
  )
}

function VariaveisFluxo({ fluxoId, variaveis, aoMudar }) {
  const abertas = variaveis.filter((variavel) => !variavel.confirmada)
  const confirmadas = variaveis.filter((variavel) => variavel.confirmada)

  if (variaveis.length === 0) {
    return <p className="text-[14.5px]">Nada muda: todas as cópias fazem exatamente o que foi gravado.</p>
  }

  return (
    <div>
      {abertas.length > 0 && (
        <ul className="space-y-4">
          {abertas.map((variavel) => (
            <Bilhete key={variavel.id} fluxoId={fluxoId} variavel={variavel} aoMudar={aoMudar} />
          ))}
        </ul>
      )}

      {confirmadas.length > 0 && (
        <dl className={`text-[14px] ${abertas.length > 0 ? 'mt-5' : ''}`}>
          {confirmadas.map((variavel) => (
            <div key={variavel.id} className="border-b border-pauta py-2">
              <dt className="font-medium text-navy">{variavel.nome}</dt>
              <dd>
                {variavel.origem}, como "{variavel.exemplo}"
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

export default VariaveisFluxo
