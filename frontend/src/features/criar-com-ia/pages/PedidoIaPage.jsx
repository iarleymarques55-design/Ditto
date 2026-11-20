import { useState } from 'react'
import { useParams } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import { SITUACOES_ABERTAS, cancelarPedido } from '../api.js'
import FolhaPassos from '../components/FolhaPassos.jsx'
import PerguntaIa from '../components/PerguntaIa.jsx'
import { usePedidoIa } from '../hooks/usePedidoIa.js'

// Ponto vermelho é o mesmo "gravando" da extensão: a IA está fazendo a tarefa por você
const SITUACOES = {
  'na-fila': { marcador: 'bg-tinta-media', texto: 'Na fila. A IA começa assim que o worker pegar o pedido.' },
  trabalhando: { marcador: 'bg-rec motion-safe:animate-piscar motion-safe:[animation-iteration-count:infinite]', texto: 'A IA está fazendo a tarefa na aba ao lado.' },
  esperando: { marcador: 'bg-sinal', texto: 'A IA parou para perguntar. Responda no recado.' },
  pronta: { marcador: 'bg-ok-texto', texto: 'Pronto. A tarefa foi para a revisão.' },
  falhou: { marcador: 'bg-rec-texto', texto: 'A IA parou antes de terminar.' },
  cancelada: { marcador: 'bg-grafite', texto: 'Cancelado. Nada virou tarefa.' },
}

function Cancelar({ pedidoId, aoMudar }) {
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function cancelar() {
    setEnviando(true)
    setErro(null)
    try {
      await cancelarPedido(pedidoId)
      aoMudar()
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div>
      <Botao variante="discreto" disabled={enviando} onClick={cancelar}>
        {enviando ? 'Cancelando...' : 'Cancelar e fechar a aba'}
      </Botao>
      {erro && (
        <p role="alert" className="mt-1 text-[13.5px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </div>
  )
}

function Situacao({ pedido, aoMudar }) {
  const situacao = SITUACOES[pedido.situacao]
  const aberto = SITUACOES_ABERTAS.includes(pedido.situacao)

  return (
    <section aria-labelledby="situacao-ia" className="space-y-4">
      <h2 id="situacao-ia" className="sr-only">
        Situação
      </h2>
      <p className="flex items-start gap-3 text-[15.5px] leading-snug text-navy" aria-live="polite">
        <span aria-hidden="true" className={`mt-[6px] size-2.5 shrink-0 rounded-full ring-4 ring-tinta-clara ${situacao.marcador}`} />
        <span>{situacao.texto}</span>
      </p>

      {pedido.situacao === 'falhou' && pedido.erro && <p className="max-w-[48ch] text-[15px] leading-relaxed">{pedido.erro}</p>}
      {aberto && pedido.ultimoAviso && pedido.situacao !== 'esperando' && <p className="text-[14px] text-grafite">{pedido.ultimoAviso}</p>}

      {pedido.situacao === 'pronta' && pedido.tarefaId && <Botao para={`/painel/tarefas/${pedido.tarefaId}`}>Revisar a tarefa</Botao>}
      {['falhou', 'cancelada'].includes(pedido.situacao) && (
        <p className="max-w-[48ch] text-[14.5px]">Para tentar de novo, use Criar com IA no topo da página e descreva o pedido com mais detalhes.</p>
      )}

      {pedido.situacao === 'esperando' && pedido.pergunta && (
        <PerguntaIa key={pedido.pergunta.texto} pedidoId={pedido.id} pergunta={pedido.pergunta} aoResponder={aoMudar} />
      )}

      {aberto && <Cancelar pedidoId={pedido.id} aoMudar={aoMudar} />}
    </section>
  )
}

function PedidoIaPage() {
  const { id } = useParams()
  const consulta = usePedidoIa(id)
  useTituloPagina(consulta.dados?.nome ?? 'Criando com IA')

  return (
    <EstadoConsulta consulta={consulta} paginaInteira>
      {(pedido) => (
        <>
          <h1 className="font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">{pedido.nome ?? 'Tarefa criada com IA'}</h1>
          <p className="mt-2 text-[14.5px] break-all text-grafite">{pedido.endereco}</p>

          <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
            <div className="order-2 lg:order-1">
              <FolhaPassos pedido={pedido} trabalhando={['na-fila', 'trabalhando'].includes(pedido.situacao)} />
            </div>
            <div className="order-1 lg:sticky lg:top-6 lg:order-2">
              <Situacao pedido={pedido} aoMudar={consulta.recarregar} />
            </div>
          </div>
        </>
      )}
    </EstadoConsulta>
  )
}

export default PedidoIaPage
