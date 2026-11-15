import { useId, useState } from 'react'
import { useNavigate } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import Modal from '../../../components/ui/Modal.jsx'
import { excluirFluxo } from '../api.js'

function ExcluirTarefa({ fluxo }) {
  const navegar = useNavigate()
  const [aberto, setAberto] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const idTitulo = useId()

  function fechar() {
    setAberto(false)
    setErro(null)
  }

  async function excluir() {
    setEnviando(true)
    setErro(null)
    try {
      await excluirFluxo(fluxo.id)
      navegar('/painel/tarefas', { replace: true })
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <>
      <Botao variante="discreto" className="!text-rec-texto !decoration-rec-texto" onClick={() => setAberto(true)}>
        Excluir esta tarefa
      </Botao>

      {aberto && (
        <Modal idTitulo={idTitulo} aoFechar={fechar} className="folha max-w-[480px] p-7">
          <h2 id={idTitulo} className="font-display text-[26px] leading-tight font-bold break-words text-navy">
            Excluir “{fluxo.nome}” para sempre?
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-grafite">
            Os passos, a agenda, as execuções e os arquivos baixados por elas serão apagados, e não há como recuperar depois.
          </p>
          <p className="mt-2 text-[14px] text-grafite">Para só tirar da lista e guardar o histórico, arquive a tarefa.</p>
          {erro && (
            <p role="alert" className="mt-3 text-[14px] font-medium text-rec-texto">
              {erro}
            </p>
          )}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Botao className="!bg-rec-texto" disabled={enviando} onClick={excluir}>
              {enviando ? 'Excluindo...' : 'Excluir para sempre'}
            </Botao>
            <Botao variante="discreto" disabled={enviando} onClick={fechar} data-foco-inicial>
              Manter a tarefa
            </Botao>
          </div>
        </Modal>
      )}
    </>
  )
}

export default ExcluirTarefa
