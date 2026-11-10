import { useId, useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import Modal from '../../../components/ui/Modal.jsx'
import { useAuth } from '../../auth/index.js'
import { excluirConta } from '../api.js'
import { classeCampo, classeRotulo, classeTitulo } from './campos.js'

function ExcluirConta() {
  const { usuario, sair } = useAuth()
  const [aberto, setAberto] = useState(false)
  const [confirmacao, setConfirmacao] = useState('')
  const [senha, setSenha] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const idTitulo = useId()
  const idConfirmacao = useId()
  const idSenha = useId()

  function fechar() {
    setAberto(false)
    setConfirmacao('')
    setSenha('')
    setErro(null)
  }

  async function excluir(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro(null)
    try {
      await excluirConta({ confirmacao, senha })
      sair()
      // Recarga completa: a conta não existe mais, e nada dela pode ficar na memória da página
      window.location.replace('/')
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <section aria-labelledby="excluir-titulo">
      <h2 id="excluir-titulo" className={classeTitulo}>
        Excluir a conta
      </h2>
      <p className="mt-1 max-w-[56ch] text-[14.5px]">
        Apaga a conta e tudo o que é dela: tarefas, execuções, arquivos, acessos e agendas. Não tem volta.
      </p>
      <Botao variante="contorno" className="mt-3 !border-rec-texto !text-rec-texto hover:!bg-[#fbf3f1]" onClick={() => setAberto(true)}>
        Excluir minha conta
      </Botao>

      {aberto && (
        <Modal idTitulo={idTitulo} aoFechar={fechar} className="folha max-w-[480px] p-7">
          <h2 id={idTitulo} className="font-display text-[26px] leading-tight font-bold text-navy">
            Excluir a conta para sempre?
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-grafite">
            Tarefas, execuções, arquivos, acessos e agendas serão apagados, e não há como recuperar depois.
          </p>
          <form onSubmit={excluir} className="mt-4 space-y-3 text-grafite">
            <div>
              <label htmlFor={idConfirmacao} className={classeRotulo}>
                Digite {usuario.email} para confirmar
              </label>
              <input
                id={idConfirmacao}
                required
                value={confirmacao}
                onChange={(evento) => setConfirmacao(evento.target.value)}
                autoComplete="off"
                data-foco-inicial
                className={classeCampo}
              />
            </div>
            {usuario.has_password && (
              <div>
                <label htmlFor={idSenha} className={classeRotulo}>
                  Sua senha
                </label>
                <input
                  id={idSenha}
                  type="password"
                  required
                  value={senha}
                  onChange={(evento) => setSenha(evento.target.value)}
                  autoComplete="current-password"
                  className={classeCampo}
                />
              </div>
            )}
            {erro && (
              <p role="alert" className="text-[14px] font-medium text-rec-texto">
                {erro}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Botao type="submit" className="!bg-rec-texto" disabled={enviando}>
                Excluir para sempre
              </Botao>
              <Botao variante="discreto" disabled={enviando} onClick={fechar}>
                Manter minha conta
              </Botao>
            </div>
          </form>
        </Modal>
      )}
    </section>
  )
}

export default ExcluirConta
