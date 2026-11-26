import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import { SITUACOES_ABERTAS, cancelarPedido, pedirParaIa } from '../api.js'
import { AvisoSemChrome } from '../../extensao/index.js'
import FolhaPassos from '../components/FolhaPassos.jsx'
import PerguntaIa from '../components/PerguntaIa.jsx'
import { usePedidoIa } from '../hooks/usePedidoIa.js'

// Ponto vermelho é o mesmo "gravando" da extensão: a IA está fazendo a tarefa por você
const SITUACOES = {
  'na-fila': { marcador: 'bg-tinta-media', texto: 'Na fila. A IA começa assim que o worker pegar o pedido.' },
  trabalhando: { marcador: 'bg-rec motion-safe:animate-piscar motion-safe:[animation-iteration-count:infinite]', texto: 'A IA está fazendo a tarefa na aba ao lado.' },
  esperando: { marcador: 'bg-sinal', texto: 'A IA precisa de uma resposta sua para seguir.' },
  pronta: { marcador: 'bg-ok-texto', texto: 'Pronto. A tarefa foi para a revisão.' },
  falhou: { marcador: 'bg-rec-texto', texto: 'A IA parou antes de terminar.' },
  cancelada: { marcador: 'bg-grafite', texto: 'Cancelado. Nada virou tarefa.' },
}

// Só endereços web viram link; o resto aparece como texto
function enderecoWeb(endereco) {
  try {
    const url = new URL(endereco)
    return ['http:', 'https:'].includes(url.protocol) ? url : null
  } catch {
    return null
  }
}

function OndeComeca({ endereco }) {
  const url = enderecoWeb(endereco)
  if (!url) return <span className="break-all">{endereco}</span>
  return (
    <a href={url.href} target="_blank" rel="noreferrer" className="underline decoration-ink/50 underline-offset-[3px] hover:text-ink">
      {url.hostname}
    </a>
  )
}

function plural(quantidade, um, varios) {
  return `${quantidade} ${quantidade === 1 ? um : varios}`
}

// Um botão que chama a API e mostra o erro logo abaixo, se houver
function Acao({ rotulo, rotuloEnviando, variante, aoClicar }) {
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function clicar() {
    setEnviando(true)
    setErro(null)
    try {
      await aoClicar()
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div>
      <Botao variante={variante} disabled={enviando} onClick={clicar}>
        {enviando ? rotuloEnviando : rotulo}
      </Botao>
      {erro && (
        <p role="alert" className="mt-1 text-[13.5px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </div>
  )
}

function Resumo({ pedido, aoMudar }) {
  const navegar = useNavigate()
  const aberto = SITUACOES_ABERTAS.includes(pedido.situacao)

  async function tentarDeNovo() {
    const novo = await pedirParaIa({ texto: pedido.texto, endereco: pedido.endereco, nome: pedido.nome ?? '' })
    navegar(`/painel/tarefas/ia/${novo.id}`)
  }

  return (
    <aside aria-label="Resumo" className="space-y-4 border-t border-line pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6">
      <p className="text-[15px] leading-relaxed text-navy">
        {plural(pedido.totalPassos, 'passo anotado', 'passos anotados')}
        {pedido.totalRespostas > 0 && (
          <>
            <br />
            {plural(pedido.totalRespostas, 'dúvida respondida', 'dúvidas respondidas')}
          </>
        )}
      </p>

      {pedido.situacao === 'falhou' && pedido.erro && <p className="max-w-[40ch] text-[14.5px] leading-relaxed text-navy">{pedido.erro}</p>}

      {pedido.situacao === 'pronta' && pedido.tarefaId && <Botao para={`/painel/tarefas/${pedido.tarefaId}`}>Revisar a tarefa</Botao>}
      {['falhou', 'cancelada'].includes(pedido.situacao) && (
        <>
          <Acao rotulo="Tentar de novo" rotuloEnviando="Enviando..." variante="primario" aoClicar={tentarDeNovo} />
          <p className="max-w-[40ch] text-[13.5px] text-grafite">Para mudar o pedido, use Criar com IA no topo da página.</p>
        </>
      )}
      {aberto && (
        <Acao
          rotulo="Cancelar e fechar a aba"
          rotuloEnviando="Cancelando..."
          variante="discreto"
          aoClicar={async () => {
            await cancelarPedido(pedido.id)
            aoMudar()
          }}
        />
      )}
    </aside>
  )
}

function PedidoIaPage() {
  const { id } = useParams()
  const consulta = usePedidoIa(id)
  useTituloPagina(consulta.dados?.nome ?? 'Criando com IA')

  return (
    <EstadoConsulta consulta={consulta} paginaInteira>
      {(pedido) => {
        const situacao = SITUACOES[pedido.situacao]
        const trabalhando = ['na-fila', 'trabalhando'].includes(pedido.situacao)
        const aberto = SITUACOES_ABERTAS.includes(pedido.situacao)

        return (
          <>
            <p className="flex items-center gap-2.5 text-[14.5px] text-navy" aria-live="polite">
              <span aria-hidden="true" className={`size-2.5 shrink-0 rounded-full ring-4 ring-tinta-clara ${situacao.marcador}`} />
              {situacao.texto}
            </p>
            <h1 className="mt-3 font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">
              {pedido.nome ?? (aberto ? 'Montando a tarefa' : 'Tarefa criada com IA')}
            </h1>
            <p className="mt-2 text-[14.5px] text-grafite">
              Começa em <OndeComeca endereco={pedido.endereco} />
            </p>

            <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_260px] lg:items-start">
              <div className="space-y-8">
                {pedido.situacao === 'na-fila' && pedido.chromeLigado === false && <AvisoSemChrome oQue="O pedido" />}
                {pedido.situacao === 'esperando' && pedido.pergunta && (
                  <PerguntaIa key={pedido.pergunta.texto} pedidoId={pedido.id} pergunta={pedido.pergunta} aoResponder={consulta.recarregar} />
                )}
                <FolhaPassos pedido={pedido} trabalhando={trabalhando} />
              </div>
              <div className="lg:sticky lg:top-6">
                <Resumo pedido={pedido} aoMudar={consulta.recarregar} />
              </div>
            </div>
          </>
        )
      }}
    </EstadoConsulta>
  )
}

export default PedidoIaPage
