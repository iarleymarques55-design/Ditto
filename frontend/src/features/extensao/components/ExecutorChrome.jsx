import { useCallback, useEffect, useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import { useAuth } from '../../auth/index.js'
import { desligarExecutor, ligarExecutor, statusDoExecutor } from '../../fluxos/extensao.js'
import { classeTitulo } from './campos.js'

const ESPERA_CONEXAO_MS = 1200
// A pessoa precisa confirmar na janela da extensão: espera até um minuto e meio por isso
const TENTATIVAS_APOS_LIGAR = 75

const ESTADOS = {
  conectado: { marcador: 'bg-ok-texto', texto: 'Ligado. A próxima execução abre uma aba ao lado da sua.' },
  'aguardando-confirmacao': {
    marcador: 'bg-sinal',
    texto: 'Confirme na janela que a extensão do Ditto abriu. Ela mostra a conta que vai ser ligada a este Chrome.',
  },
  conectando: {
    marcador: 'bg-sinal',
    texto: 'Ligado, esperando o Ditto responder. As tarefas ficam na fila até ele voltar.',
  },
  desconectado: {
    marcador: 'bg-sinal',
    texto: 'Ligado, esperando o Ditto responder. As tarefas ficam na fila até ele voltar.',
  },
  recusado: {
    marcador: 'bg-grafite',
    texto: 'Desligado: a ligação expirou ou foi encerrada, por exemplo depois de trocar a senha. Ligue de novo.',
  },
  'em-uso': {
    marcador: 'bg-sinal',
    texto: 'Outro Chrome já está ligado nesta conta, e as tarefas rodam nele. Para usar este, desligue o outro.',
  },
  'sem-token': { marcador: 'bg-grafite', texto: 'Desligado. As tarefas rodam no navegador do Ditto, sem as suas contas.' },
  'sem-resposta': { marcador: 'bg-grafite', texto: 'A extensão não respondeu. Recarregue a página.' },
  'sem-extensao': {
    marcador: 'bg-grafite',
    texto: 'A extensão do Ditto não está instalada neste Chrome. Siga os passos acima e recarregue a página.',
  },
}

const LIGADO = ['conectado', 'conectando', 'desconectado', 'em-uso']
const AGUARDANDO = ['aguardando-confirmacao', 'conectando', 'desconectado']

const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms))

function ExecutorChrome() {
  const { usuario } = useAuth()
  const [status, setStatus] = useState(null)
  const [ocupado, setOcupado] = useState(null)
  const [erro, setErro] = useState(null)

  const atualizar = useCallback(async () => setStatus(await statusDoExecutor()), [])

  useEffect(() => {
    // A extensão marca a página logo ao carregar; o primeiro estado chega numa volta só
    let ativo = true
    statusDoExecutor().then((atual) => ativo && setStatus(atual))
    window.addEventListener('focus', atualizar)
    return () => {
      ativo = false
      window.removeEventListener('focus', atualizar)
    }
  }, [atualizar])

  async function ligar() {
    setOcupado('ligando')
    setErro(null)
    try {
      let atual = await ligarExecutor(usuario?.email)
      setStatus(atual)
      // A ligação só começa depois que a pessoa confirma na extensão, e leva um instante
      for (let tentativa = 0; AGUARDANDO.includes(atual) && tentativa < TENTATIVAS_APOS_LIGAR; tentativa += 1) {
        await esperar(ESPERA_CONEXAO_MS)
        atual = await statusDoExecutor()
        setStatus(atual)
      }
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setOcupado(null)
    }
  }

  async function desligar() {
    setOcupado('desligando')
    setErro(null)
    try {
      await desligarExecutor()
      setStatus(await statusDoExecutor())
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setOcupado(null)
    }
  }

  const estado = ESTADOS[status]
  const podeLigar = status && !['sem-extensao', 'sem-resposta'].includes(status)
  const desligado = ['sem-token', 'recusado'].includes(status)
  const ligado = LIGADO.includes(status)

  return (
    <section aria-labelledby="executor-titulo">
      <h2 id="executor-titulo" className={classeTitulo}>
        Executar no meu Chrome
      </h2>
      <p className="mt-1 max-w-[56ch] text-[14.5px]">
        As tarefas da sua conta rodam neste Chrome, em uma aba ao lado da que você está usando e com as contas que já estão logadas nele.
      </p>

      <p className="mt-4 flex max-w-[56ch] items-start gap-3 text-[15px] text-navy" aria-live="polite">
        <span aria-hidden="true" className={`mt-[7px] size-2.5 shrink-0 rounded-full ring-4 ring-tinta-clara ${estado?.marcador ?? 'bg-tinta-media'}`} />
        <span>{estado?.texto ?? 'Consultando a extensão...'}</span>
      </p>

      {podeLigar && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Botao variante={desligado ? 'primario' : 'discreto'} disabled={Boolean(ocupado)} onClick={ligar}>
            {ocupado === 'ligando' ? 'Ligando...' : desligado ? 'Ligar neste Chrome' : 'Ligar de novo'}
          </Botao>
          {ligado && (
            <Botao variante="contorno" disabled={Boolean(ocupado)} onClick={desligar}>
              {ocupado === 'desligando' ? 'Desligando...' : 'Desligar este Chrome'}
            </Botao>
          )}
        </div>
      )}
      {erro && (
        <p role="alert" className="mt-2 text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}

      <p className="mt-3 max-w-[56ch] text-[13.5px] text-grafite">
        Enquanto uma tarefa roda, o Chrome mostra a faixa “começou a depurar este navegador”. Clicar em Cancelar nela para a linha que estava rodando. Sair do painel também desliga este Chrome.
      </p>
    </section>
  )
}

export default ExecutorChrome
