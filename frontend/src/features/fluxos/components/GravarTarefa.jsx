import { useId, useState } from 'react'
import RecordIcon from '../../../components/landing/RecordIcon.jsx'
import Botao from '../../../components/ui/Botao.jsx'
import Modal from '../../../components/ui/Modal.jsx'
import { consultarExtensao, extensaoInstalada, iniciarGravacao } from '../extensao.js'

const classeCampo = 'mt-1 min-h-11 w-full rounded-[2px] border border-grafite/60 bg-papel-folha px-3 text-[15px] text-navy'
const classeTitulo = 'font-display text-[26px] leading-tight font-bold text-navy'
const classeTexto = 'mt-3 text-[15px] leading-relaxed text-grafite'

function normalizarEndereco(texto) {
  const limpo = texto.trim()
  const comProtocolo = /^[a-z][a-z0-9+.-]*:\/\//i.test(limpo) ? limpo : `https://${limpo}`
  try {
    const url = new URL(comProtocolo)
    const protocoloValido = ['http:', 'https:'].includes(url.protocol)
    const hostValido = url.hostname.includes('.') || url.hostname === 'localhost'
    return protocoloValido && hostValido ? url.href : null
  } catch {
    return null
  }
}

function SemExtensao({ idTitulo, aoFechar }) {
  return (
    <>
      <h2 id={idTitulo} className={classeTitulo}>
        Falta instalar o gravador
      </h2>
      <p className={classeTexto}>É uma extensão do Chrome. Ela só grava a aba que você abrir por aqui.</p>
      <ol className="mt-4 list-decimal space-y-2 pl-5 text-[15px] leading-relaxed text-navy">
        <li>
          Abra <code className="font-mono text-[13.5px]">chrome://extensions</code> em uma aba nova.
        </li>
        <li>Ligue o <strong>Modo do desenvolvedor</strong>, no canto superior direito.</li>
        <li>
          Clique em <strong>Carregar sem compactação</strong> e escolha a pasta{' '}
          <code className="font-mono text-[13.5px]">extension</code> do projeto.
        </li>
        <li>Volte aqui e recarregue a página.</li>
      </ol>
      <p className="mt-3 text-[14px] text-grafite">Também funciona no Edge e no Brave.</p>
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Botao data-foco-inicial onClick={() => window.location.reload()}>
          Já instalei, recarregar
        </Botao>
        <Botao variante="discreto" onClick={aoFechar}>
          Fechar
        </Botao>
      </div>
    </>
  )
}

function Formulario({ idTitulo, aoFechar, aoIniciar }) {
  const [nome, setNome] = useState('')
  const [endereco, setEndereco] = useState('')
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const idNome = useId()
  const idEndereco = useId()

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
      await iniciarGravacao({ nome: nome.trim(), url })
      aoIniciar()
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={enviar}>
      <h2 id={idTitulo} className={classeTitulo}>
        Gravar uma tarefa
      </h2>
      <p className={classeTexto}>
        Uma aba nova abre neste endereço. Faça a tarefa como sempre faz, e o Ditto aprende olhando. Senhas não são gravadas.
      </p>
      <p className="mt-2 text-[14.5px] leading-relaxed text-navy">
        Se o site pede login, saia da sua conta antes de começar, para o login entrar na gravação.
      </p>

      <div className="mt-5">
        <label htmlFor={idNome} className="text-[14px] font-medium text-navy">
          Nome da tarefa
        </label>
        <input
          id={idNome}
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
          required
          maxLength={160}
          autoComplete="off"
          placeholder="Consultar situação no portal"
          data-foco-inicial
          className={classeCampo}
        />
      </div>
      <div className="mt-4">
        <label htmlFor={idEndereco} className="text-[14px] font-medium text-navy">
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
          placeholder="https://portal.exemplo.gov.br"
          className={classeCampo}
        />
      </div>

      {erro && (
        <p role="alert" className="mt-3 text-[14.5px] font-medium text-rec-texto">
          {erro}
        </p>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Botao type="submit" disabled={enviando}>
          <RecordIcon className="size-4" />
          {enviando ? 'Abrindo...' : 'Começar a gravar'}
        </Botao>
        <Botao variante="discreto" onClick={aoFechar}>
          Cancelar
        </Botao>
      </div>
    </form>
  )
}

function Aviso({ idTitulo, titulo, aoFechar, children }) {
  return (
    <>
      <h2 id={idTitulo} className={classeTitulo}>
        {titulo}
      </h2>
      {children}
      <Botao variante="contorno" className="mt-5" data-foco-inicial onClick={aoFechar}>
        Entendi
      </Botao>
    </>
  )
}

function GravarTarefa() {
  const [fase, setFase] = useState(null)
  const [nomeEmAndamento, setNomeEmAndamento] = useState('')
  const idTitulo = useId()
  const fechar = () => setFase(null)

  async function abrir() {
    if (!extensaoInstalada()) {
      setFase('sem-extensao')
      return
    }
    setFase('verificando')
    const estado = await consultarExtensao()
    if (!estado) {
      setFase('sem-resposta')
    } else if (estado.recording) {
      setNomeEmAndamento(estado.name)
      setFase('em-andamento')
    } else {
      setFase('formulario')
    }
  }

  return (
    <>
      <Botao variante="contorno" onClick={abrir}>
        <RecordIcon className="size-4" />
        Gravar tarefa
      </Botao>

      {fase && (
        <Modal key={fase} idTitulo={idTitulo} aoFechar={fechar} className="folha max-w-[480px] p-7">
          {fase === 'verificando' && (
            <h2 id={idTitulo} className={classeTitulo}>
              Procurando o gravador...
            </h2>
          )}
          {fase === 'sem-extensao' && <SemExtensao idTitulo={idTitulo} aoFechar={fechar} />}
          {fase === 'formulario' && <Formulario idTitulo={idTitulo} aoFechar={fechar} aoIniciar={() => setFase('gravando')} />}
          {fase === 'sem-resposta' && (
            <Aviso idTitulo={idTitulo} titulo="O gravador não respondeu" aoFechar={fechar}>
              <p className={classeTexto}>Recarregue esta página e tente de novo. Se continuar, recarregue a extensão em chrome://extensions.</p>
            </Aviso>
          )}
          {fase === 'em-andamento' && (
            <Aviso idTitulo={idTitulo} titulo="Já tem uma gravação aberta" aoFechar={fechar}>
              <p className={classeTexto}>
                "{nomeEmAndamento}" ainda está gravando. Termine na barra da aba gravada ou clique no ícone do Ditto, na barra do navegador,
                para salvar ou descartar.
              </p>
            </Aviso>
          )}
          {fase === 'gravando' && (
            <Aviso idTitulo={idTitulo} titulo="Pode começar" aoFechar={fechar}>
              <p className={classeTexto}>A gravação está na aba nova. Faça a tarefa lá, no seu ritmo.</p>
              <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[15px] leading-relaxed text-navy">
                <li>
                  Precisa guardar um valor da tela? Clique em <strong>Capturar dado</strong> na barra e depois no valor.
                </li>
                <li>
                  A cada ação, a barra mostra o que foi anotado. Se uma ação sua não aparecer, ela não será repetida.
                </li>
                <li>
                  Ao terminar, clique em <strong>Parar e salvar</strong>. A tarefa abre aqui para você revisar.
                </li>
              </ul>
            </Aviso>
          )}
        </Modal>
      )}
    </>
  )
}

export default GravarTarefa
