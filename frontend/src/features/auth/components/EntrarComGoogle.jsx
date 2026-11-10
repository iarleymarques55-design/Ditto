import { useEffect, useRef, useState } from 'react'
import { EM_DESENVOLVIMENTO, GOOGLE_CLIENT_ID } from '../../../config/env.js'

const SCRIPT_GOOGLE = 'https://accounts.google.com/gsi/client'

let carregamento
function carregarGoogle() {
  carregamento ??= new Promise((resolver, rejeitar) => {
    const script = document.createElement('script')
    script.src = SCRIPT_GOOGLE
    script.async = true
    script.onload = () => resolver(window.google)
    script.onerror = () => {
      carregamento = undefined
      rejeitar(new Error('Não foi possível carregar o login do Google.'))
    }
    document.head.appendChild(script)
  })
  return carregamento
}

// As cores da marca do Google são fixas pela regra de uso dela, por isso não usam os tokens
function LogoGoogle() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" className="size-[18px]">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5Z"
      />
      <path
        fill="#FF3D00"
        d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7Z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44Z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5Z"
      />
    </svg>
  )
}

const classeBotaoProprio =
  'flex h-11 w-full items-center justify-center gap-2.5 rounded-[10px] border border-tinta-media bg-card text-[15px] font-medium text-navy'

// O botão oficial do Google mostra "Fazer login como <nome>" sozinho quando a pessoa já tem sessão.
function BotaoOficial({ cadastro, texto, aoReceberCredencial, aoFalhar }) {
  const alvo = useRef(null)
  const [pronto, setPronto] = useState(false)

  // Em ref para não reiniciar o Google a cada render do formulário
  const callbacks = useRef({ aoReceberCredencial, aoFalhar })
  useEffect(() => {
    callbacks.current = { aoReceberCredencial, aoFalhar }
  })

  useEffect(() => {
    let ativo = true

    carregarGoogle()
      .then((google) => {
        if (!ativo || !alvo.current) return
        google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: ({ credential }) => callbacks.current.aoReceberCredencial(credential),
          ux_mode: 'popup',
        })
        google.accounts.id.renderButton(alvo.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          shape: 'rectangular',
          text: cadastro ? 'signup_with' : 'signin_with',
          logo_alignment: 'center',
          locale: 'pt-BR',
          width: Math.min(alvo.current.offsetWidth, 400),
        })
        setPronto(true)
      })
      .catch((falha) => {
        if (ativo) callbacks.current.aoFalhar(falha.message)
      })

    return () => {
      ativo = false
    }
  }, [cadastro])

  return (
    <div className="relative h-11 w-full">
      {/* Mesmo tamanho enquanto o script do Google carrega, para o modal não pular */}
      {!pronto && (
        <div className={`absolute inset-0 ${classeBotaoProprio}`}>
          <LogoGoogle />
          {texto}
        </div>
      )}
      <div ref={alvo} className="flex w-full justify-center [color-scheme:light]" />
    </div>
  )
}

function EntrarComGoogle({ cadastro = false, aoReceberCredencial, aoFalhar }) {
  // Sem client ID o Google recusa o login: em produção o botão nem aparece
  if (!GOOGLE_CLIENT_ID && !EM_DESENVOLVIMENTO) return null

  const texto = cadastro ? 'Cadastrar com Google' : 'Entrar com Google'

  return (
    <>
      {GOOGLE_CLIENT_ID ? (
        <BotaoOficial
          cadastro={cadastro}
          texto={texto}
          aoReceberCredencial={aoReceberCredencial}
          aoFalhar={aoFalhar}
        />
      ) : (
        <button
          type="button"
          onClick={() => aoFalhar('Login com Google não configurado: defina VITE_GOOGLE_CLIENT_ID no frontend/.env.')}
          className={`${classeBotaoProprio} hover:bg-card-soft motion-safe:transition-colors`}
        >
          <LogoGoogle />
          {texto}
        </button>
      )}
      <div className="my-5 flex items-center gap-3 text-[13px] text-body">
        <span aria-hidden="true" className="h-px flex-1 bg-tinta-clara" />
        ou continue com e-mail
        <span aria-hidden="true" className="h-px flex-1 bg-tinta-clara" />
      </div>
    </>
  )
}

export default EntrarComGoogle
