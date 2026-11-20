import { PenLine } from 'lucide-react'
import { useId, useState } from 'react'
import { useNavigate } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import Modal from '../../../components/ui/Modal.jsx'
import { normalizarEndereco } from '../../../lib/endereco.js'
import { statusDoExecutor } from '../../fluxos/extensao.js'
import { pedirParaIa } from '../api.js'

const classeCampo = 'mt-1 w-full rounded-[2px] border border-grafite/60 bg-papel-folha px-3 text-[15px] text-navy'
const classeTitulo = 'font-display text-[26px] leading-tight font-bold text-navy'
const classeTexto = 'mt-3 text-[15px] leading-relaxed text-grafite'
const classeRotulo = 'text-[14px] font-medium text-navy'

const EXEMPLO =
  'Pesquise o time Boston Bruins no campo de busca e guarde a tabela de resultados.'

// A IA só monta tarefas no Chrome da pessoa: sem o executor ligado, não há onde ela navegar
const MOTIVOS_SEM_EXECUTOR = {
  'sem-extensao': 'A extensão do Ditto não está instalada neste Chrome.',
  'sem-resposta': 'A extensão do Ditto não respondeu. Recarregue esta página.',
  'sem-token': 'O executor está desligado.',
  recusado: 'A ligação do executor expirou.',
  conectando: 'O executor está ligado, mas o worker não respondeu. Confira se ele está no ar.',
  desconectado: 'O executor está ligado, mas o worker não respondeu. Confira se ele está no ar.',
}

function SemExecutor({ idTitulo, motivo, aoFechar }) {
  return (
    <>
      <h2 id={idTitulo} className={classeTitulo}>
        Ligue o executor primeiro
      </h2>
      <p className={classeTexto}>
        A IA monta a tarefa numa aba ao lado, neste Chrome, para usar as contas em que você já entrou. {motivo}
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Botao para="/painel/conta" data-foco-inicial onClick={aoFechar}>
          Abrir a página da conta
        </Botao>
        <Botao variante="discreto" onClick={aoFechar}>
          Fechar
        </Botao>
      </div>
    </>
  )
}

function Formulario({ idTitulo, aoFechar }) {
  const navegar = useNavigate()
  const [texto, setTexto] = useState('')
  const [endereco, setEndereco] = useState('')
  const [nome, setNome] = useState('')
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const idTexto = useId()
  const idDica = useId()
  const idEndereco = useId()
  const idNome = useId()

  async function enviar(evento) {
    evento.preventDefault()
    const url = normalizarEndereco(endereco)
    if (!url) {
      setErro('Este endereço não parece válido. Exemplo: https://portal.exemplo.gov.br')
      return
    }
    setEnviando(true)
    setErro(null)
    try {
      const pedido = await pedirParaIa({ texto: texto.trim(), endereco: url, nome: nome.trim() })
      aoFechar()
      navegar(`/painel/tarefas/ia/${pedido.id}`)
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={enviar}>
      <h2 id={idTitulo} className={classeTitulo}>
        Criar uma tarefa com IA
      </h2>
      <p className={classeTexto}>
        Escreva o que a tarefa faz. A IA abre o site numa aba ao lado e faz uma vez, passo a passo. Quando tiver dúvida, ela pergunta aqui no
        painel. Senhas ela não digita.
      </p>

      <div className="mt-5">
        <label htmlFor={idTexto} className={classeRotulo}>
          O que a tarefa faz
        </label>
        <textarea
          id={idTexto}
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          required
          minLength={10}
          maxLength={2000}
          rows={4}
          placeholder={EXEMPLO}
          aria-describedby={idDica}
          data-foco-inicial
          className={`${classeCampo} resize-y py-2 leading-relaxed`}
        />
        <p id={idDica} className="mt-1 text-[13.5px] text-grafite">
          Diga o que digitar, onde clicar e quais dados guardar.
        </p>
      </div>
      <div className="mt-4">
        <label htmlFor={idEndereco} className={classeRotulo}>
          Onde a tarefa começa
        </label>
        <input
          id={idEndereco}
          value={endereco}
          onChange={(evento) => setEndereco(evento.target.value)}
          required
          maxLength={2000}
          inputMode="url"
          autoComplete="off"
          spellCheck="false"
          placeholder="https://www.scrapethissite.com/pages/forms/"
          className={`${classeCampo} min-h-11`}
        />
      </div>
      <div className="mt-4">
        <label htmlFor={idNome} className={classeRotulo}>
          Nome da tarefa <span className="font-normal text-grafite">(opcional, a IA sugere um)</span>
        </label>
        <input
          id={idNome}
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
          maxLength={160}
          autoComplete="off"
          className={`${classeCampo} min-h-11`}
        />
      </div>

      {erro && (
        <p role="alert" className="mt-3 text-[14.5px] font-medium text-rec-texto">
          {erro}
        </p>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Botao type="submit" disabled={enviando}>
          {enviando ? 'Enviando...' : 'Criar tarefa'}
        </Botao>
        <Botao variante="discreto" onClick={aoFechar}>
          Cancelar
        </Botao>
      </div>
    </form>
  )
}

function CriarComIa() {
  const [fase, setFase] = useState(null)
  const [motivo, setMotivo] = useState('')
  const idTitulo = useId()
  const fechar = () => setFase(null)

  async function abrir() {
    setFase('verificando')
    const status = await statusDoExecutor()
    if (status === 'conectado') {
      setFase('formulario')
    } else {
      setMotivo(MOTIVOS_SEM_EXECUTOR[status] ?? '')
      setFase('sem-executor')
    }
  }

  return (
    <>
      <Botao variante="contorno" onClick={abrir}>
        <PenLine aria-hidden="true" className="size-4" />
        Criar com IA
      </Botao>

      {fase && (
        <Modal key={fase} idTitulo={idTitulo} aoFechar={fechar} className="folha max-w-[520px] p-7">
          {fase === 'verificando' && (
            <h2 id={idTitulo} className={classeTitulo}>
              Procurando o executor...
            </h2>
          )}
          {fase === 'sem-executor' && <SemExecutor idTitulo={idTitulo} motivo={motivo} aoFechar={fechar} />}
          {fase === 'formulario' && <Formulario idTitulo={idTitulo} aoFechar={fechar} />}
        </Modal>
      )}
    </>
  )
}

export default CriarComIa
