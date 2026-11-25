import { useEffect, useId, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { confirmarEmail, reenviarCodigo } from '../api.js'
import { BotaoEnviar, Campo, MensagemErro } from '../components/CamposAuth.jsx'
import ModalAuth from '../components/ModalAuth.jsx'
import { useAuth } from '../hooks/useAuth.js'

// O servidor aceita um código por minuto: o botão espera o mesmo tempo
const ESPERA_REENVIO_S = 60

function ConfirmarEmailPage() {
  const { state } = useLocation()
  const navegar = useNavigate()
  const { iniciarSessao } = useAuth()
  const idCodigo = useId()

  // Quem chega aqui pelo cadastro ou pelo login já traz o e-mail; quem abriu o endereço direto digita
  const [email, setEmail] = useState(state?.email ?? '')
  const emailConhecido = Boolean(state?.email)
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState(null)
  const [aviso, setAviso] = useState(state?.aviso ?? null)
  const [ocupado, setOcupado] = useState(false)
  const [espera, setEspera] = useState(emailConhecido ? ESPERA_REENVIO_S : 0)
  const enviando = useRef(false)

  useEffect(() => {
    if (espera <= 0) return undefined
    const relogio = setTimeout(() => setEspera(espera - 1), 1000)
    return () => clearTimeout(relogio)
  }, [espera])

  async function confirmar(valor) {
    if (enviando.current || valor.length !== 6 || !email) return
    enviando.current = true
    setErro(null)
    setOcupado(true)
    try {
      iniciarSessao(await confirmarEmail({ email, codigo: valor }))
      navegar('/painel', { replace: true })
    } catch (falha) {
      setErro(falha.message)
      setCodigo('')
    } finally {
      enviando.current = false
      setOcupado(false)
    }
  }

  async function reenviar() {
    if (!email) {
      setErro('Digite o e-mail da conta para receber um código novo.')
      return
    }
    setErro(null)
    try {
      await reenviarCodigo(email)
      setAviso(`Se ${email} está esperando confirmação, um código novo chega em instantes. Só o último código vale.`)
      setEspera(ESPERA_REENVIO_S)
    } catch (falha) {
      setErro(falha.message)
    }
  }

  function digitar(evento) {
    // Aceita o código colado com espaço ou traço ("482 913"); fica só com os números
    const valor = evento.target.value.replace(/\D/g, '').slice(0, 6)
    setCodigo(valor)
    if (valor.length === 6) confirmar(valor)
  }

  return (
    <ModalAuth
      titulo="Confirme seu e-mail"
      subtitulo={
        emailConhecido
          ? `Enviamos um código de 6 dígitos para ${email}. Ele vale por 15 minutos.`
          : 'Digite o e-mail da conta e o código de 6 dígitos que enviamos para ele.'
      }
      pergunta="E-mail errado?"
      trocarPara="/criar-conta"
      trocarTexto="Criar a conta de novo"
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(evento) => {
          evento.preventDefault()
          confirmar(codigo)
        }}
      >
        {!emailConhecido && (
          <Campo
            rotulo="E-mail"
            type="email"
            placeholder="seu.email@empresa.com.br"
            autoComplete="email"
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
          />
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor={idCodigo} className="text-[14px] font-medium text-navy">
            Código
          </label>
          <input
            id={idCodigo}
            required
            value={codigo}
            onChange={digitar}
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="000000"
            aria-describedby={`${idCodigo}-dica`}
            data-foco-inicial={emailConhecido ? true : undefined}
            className="h-14 w-full rounded-[10px] border border-tinta-media bg-card pr-3.5 pl-[calc(0.875rem+0.45em)] text-center font-display text-[28px] font-bold tracking-[0.45em] text-navy tabular-nums outline-none placeholder:text-tinta-media focus:border-ink focus:ring-4 focus:ring-ink/15 motion-safe:transition-shadow"
          />
          <p id={`${idCodigo}-dica`} className="text-[13px] text-body">
            Não chegou? Confira a caixa de spam.
          </p>
        </div>

        {aviso && (
          <output className="block rounded-[10px] bg-card-soft px-3.5 py-2.5 text-[14px] text-navy">
            {aviso}
          </output>
        )}
        <MensagemErro>{erro}</MensagemErro>

        <BotaoEnviar ocupado={ocupado}>Confirmar e entrar</BotaoEnviar>

        <button
          type="button"
          onClick={reenviar}
          disabled={espera > 0}
          className="-my-1 inline-flex min-h-11 items-center justify-center text-[14px] font-medium text-ink underline-offset-2 hover:underline disabled:cursor-default disabled:text-body disabled:no-underline"
        >
          {espera > 0 ? `Reenviar código em ${espera} s` : 'Reenviar código'}
        </button>
      </form>
    </ModalAuth>
  )
}

export default ConfirmarEmailPage
