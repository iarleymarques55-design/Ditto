import { useId, useState } from 'react'
import { useNavigate } from 'react-router'
import RecordIcon from '../../../components/landing/RecordIcon.jsx'
import Botao from '../../../components/ui/Botao.jsx'
import Modal from '../../../components/ui/Modal.jsx'
import { importarGravacao } from '../api.js'

const LIMITE_BYTES = 5 * 1024 * 1024

// A extensão que grava ainda não existe: por enquanto, a gravação entra por um arquivo JSON.
function ImportarGravacao() {
  const navegar = useNavigate()
  const [aberto, setAberto] = useState(false)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const idTitulo = useId()

  function fechar() {
    setAberto(false)
    setErro(null)
  }

  async function importar(arquivo) {
    setErro(null)
    if (arquivo.size > LIMITE_BYTES) {
      setErro('O arquivo passa de 5 MB.')
      return
    }

    let gravacao
    try {
      gravacao = JSON.parse(await arquivo.text())
    } catch {
      setErro('Este arquivo não é um JSON válido.')
      return
    }

    setEnviando(true)
    try {
      const { id } = await importarGravacao(gravacao)
      fechar()
      navegar(`/painel/tarefas/${id}`)
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <>
      <Botao variante="contorno" onClick={() => setAberto(true)}>
        <RecordIcon className="size-4" />
        Gravar tarefa
      </Botao>

      {aberto && (
        <Modal idTitulo={idTitulo} aoFechar={fechar} className="folha max-w-[480px] p-7">
          <h2 id={idTitulo} className="font-display text-[26px] leading-tight font-bold text-navy">
            Trazer uma gravação
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-grafite">
            A extensão do Chrome que grava sozinha ainda está em construção. Por enquanto, a gravação entra por um arquivo
            JSON. Senhas que estiverem nele são descartadas.
          </p>

          <label className="mt-5 flex min-h-11 w-fit cursor-pointer items-center rounded-full bg-ink px-5 text-[14.5px] font-medium text-white shadow-botao focus-within:outline-2 focus-within:outline-offset-3 focus-within:outline-ink hover:brightness-110">
            {enviando ? 'Enviando...' : 'Escolher arquivo .json'}
            <input
              type="file"
              accept=".json,application/json"
              className="sr-only"
              disabled={enviando}
              data-foco-inicial
              onChange={(evento) => {
                const [arquivo] = evento.target.files
                if (arquivo) importar(arquivo)
                evento.target.value = ''
              }}
            />
          </label>

          {erro && (
            <p role="alert" className="mt-3 text-[14.5px] font-medium text-rec-texto">
              {erro}
            </p>
          )}

          <Botao variante="discreto" className="mt-3" onClick={fechar}>
            Fechar
          </Botao>
        </Modal>
      )}
    </>
  )
}

export default ImportarGravacao
