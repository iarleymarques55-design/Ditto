import { useId, useState } from 'react'
import Fita from '../../../components/landing/mesa/Fita.jsx'
import Botao from '../../../components/ui/Botao.jsx'
import { responderIa } from '../api.js'

// A dúvida da IA, colada na mesa como os pedidos de ajuda das execuções
function PerguntaIa({ pedidoId, pergunta, aoResponder }) {
  const [outra, setOutra] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const idTitulo = useId()
  const idOutra = useId()

  async function responder(resposta) {
    setEnviando(true)
    setErro(null)
    try {
      await responderIa(pedidoId, resposta)
      aoResponder()
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  function enviarOutra(evento) {
    evento.preventDefault()
    if (outra.trim()) responder(outra.trim())
  }

  return (
    <section
      aria-labelledby={idTitulo}
      className="post-it relative max-w-[620px] px-5 pt-7 pb-5 motion-safe:animate-carimbar"
    >
      <Fita className="-top-2.5 left-1/2 -translate-x-1/2 -rotate-2" />
      <h2 id={idTitulo} className="text-[13.5px] font-medium text-grafite">
        A IA está esperando você
      </h2>
      <p aria-live="polite" className="mt-1 font-display text-[19px] leading-snug font-bold text-navy">
        {pergunta.texto}
      </p>

      {pergunta.opcoes.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {pergunta.opcoes.map((opcao, indice) => (
            <Botao
              key={opcao}
              variante={indice === 0 ? 'primario' : 'contorno'}
              disabled={enviando}
              onClick={() => responder(opcao)}
              className="!px-4 text-left !whitespace-normal"
            >
              {opcao}
            </Botao>
          ))}
        </div>
      )}

      <form onSubmit={enviarOutra} className="mt-4">
        <label htmlFor={idOutra} className="text-[13.5px] text-navy">
          {pergunta.opcoes.length > 0 ? 'Ou escreva outra resposta' : 'Sua resposta'}
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id={idOutra}
            value={outra}
            onChange={(evento) => setOutra(evento.target.value)}
            maxLength={300}
            autoComplete="off"
            className="min-h-11 min-w-0 flex-1 rounded-[2px] border border-grafite/50 bg-papel-folha px-3 text-[15px] text-navy"
          />
          <Botao type="submit" variante="contorno" disabled={enviando || !outra.trim()} className="!px-4">
            Responder
          </Botao>
        </div>
        <p className="mt-1.5 text-[13px] text-grafite">Nunca escreva senhas aqui. Para entrar numa conta, use a aba do Ditto.</p>
      </form>

      {erro && (
        <p role="alert" className="mt-2 text-[13.5px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </section>
  )
}

export default PerguntaIa
