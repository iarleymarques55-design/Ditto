import { useId, useState } from 'react'
import { Link } from 'react-router'
import Fita from '../../../components/landing/mesa/Fita.jsx'
import Botao from '../../../components/ui/Botao.jsx'
import { responderPedido } from '../api.js'

const INCLINACOES = ['lg:-rotate-[1.2deg]', 'lg:rotate-[0.9deg]', 'lg:-rotate-[0.5deg]']

const ACOES = {
  confirmar: [
    { acao: 'confirm', rotulo: 'Confirmar', variante: 'primario' },
    { acao: 'decline', rotulo: 'Não seguir', variante: 'contorno' },
  ],
  escolher: [
    { acao: 'choose', rotulo: 'Usar este caminho', variante: 'primario' },
    { acao: 'skip', rotulo: 'Pular esta linha', variante: 'contorno' },
  ],
  captcha: [
    { acao: 'retry', rotulo: 'Tentar de novo', variante: 'primario' },
    { acao: 'skip', rotulo: 'Pular esta linha', variante: 'contorno' },
  ],
  incerto: [
    { acao: 'retry', rotulo: 'Tentar de novo', variante: 'primario' },
    { acao: 'skip', rotulo: 'Pular esta linha', variante: 'contorno' },
  ],
}

// Post-it colado na folha: a única coisa no painel que pede uma decisão de alguém.
function PedidoAjuda({ pedido, indice = 0, aoResponder }) {
  const [opcao, setOpcao] = useState(pedido.opcoes?.[0]?.id)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const idTitulo = useId()

  async function responder(acao) {
    setEnviando(true)
    setErro(null)
    try {
      await responderPedido(pedido.id, { acao, opcao })
      aoResponder?.()
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <li aria-labelledby={idTitulo} className={`post-it relative flex flex-col px-5 pt-6 pb-4 ${INCLINACOES[indice % INCLINACOES.length]}`}>
      <Fita className="-top-2.5 left-1/2 -translate-x-1/2 -rotate-1" />
      <h3 id={idTitulo} className="font-display text-[18px] leading-snug font-bold text-navy italic">
        {pedido.titulo}
      </h3>
      <p className="mt-2 text-[14px] leading-snug text-grafite">{pedido.texto}</p>

      {pedido.opcoes.length > 0 && (
        <fieldset className="mt-3">
          <legend className="sr-only">Opções encontradas na página</legend>
          {pedido.opcoes.map((candidata) => (
            <label key={candidata.id} className="flex min-h-11 cursor-pointer items-center gap-2.5 text-[14px] text-navy">
              <input
                type="radio"
                name={`opcao-${pedido.id}`}
                checked={opcao === candidata.id}
                onChange={() => setOpcao(candidata.id)}
                className="size-[18px] accent-ink"
              />
              <span>
                {candidata.texto} <span className="text-grafite">({candidata.parecido}% parecido)</span>
              </span>
            </label>
          ))}
        </fieldset>
      )}

      <div className="pt-4">
        <div className="flex flex-wrap gap-2">
          {ACOES[pedido.tipo].map(({ acao, rotulo, variante }) => (
            <Botao key={acao} variante={variante} disabled={enviando} onClick={() => responder(acao)} className="!px-4">
              {rotulo}
            </Botao>
          ))}
        </div>
        {erro && (
          <p role="alert" className="mt-2 text-[13px] text-rec-texto">
            {erro}
          </p>
        )}
        <Link
          to={`/painel/execucoes/${pedido.execucaoId}`}
          className="mt-3 inline-flex min-h-8 items-center text-[13px] text-navy underline decoration-ink/60 underline-offset-[3px] hover:text-ink"
        >
          {pedido.fluxoNome}, linha {pedido.posicaoItem}
        </Link>
      </div>
    </li>
  )
}

export default PedidoAjuda
