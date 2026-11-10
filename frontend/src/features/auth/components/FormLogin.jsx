import { useState } from 'react'
import { entrar, entrarComGoogle } from '../api.js'
import { useEnvioAuth } from '../hooks/useEnvioAuth.js'
import { BotaoEnviar, Campo, CampoSenha, MensagemErro } from './CamposAuth.jsx'
import EntrarComGoogle from './EntrarComGoogle.jsx'

function FormLogin() {
  const { erro, ocupado, enviar, mostrarErro } = useEnvioAuth()
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')

  return (
    <>
      <EntrarComGoogle
        aoReceberCredencial={(credencial) => enviar(() => entrarComGoogle(credencial))}
        aoFalhar={mostrarErro}
      />

      <form
        className="flex flex-col gap-4"
        onSubmit={(evento) => {
          evento.preventDefault()
          enviar(() => entrar({ email, senha }))
        }}
      >
        <Campo
          rotulo="E-mail"
          type="email"
          placeholder="seu.email@empresa.com.br"
          autoComplete="email"
          value={email}
          onChange={(evento) => setEmail(evento.target.value)}
          data-foco-inicial
        />
        <CampoSenha
          rotulo="Senha"
          placeholder="Digite sua senha"
          autoComplete="current-password"
          value={senha}
          onChange={(evento) => setSenha(evento.target.value)}
        />
        <MensagemErro>{erro}</MensagemErro>
        <BotaoEnviar ocupado={ocupado}>Entrar</BotaoEnviar>
      </form>
    </>
  )
}

export default FormLogin
