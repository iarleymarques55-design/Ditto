import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from './useAuth.js'

// Estado comum dos formulários de entrada: envio em andamento, erro e destino depois do sucesso.
// E-mail ainda não confirmado não é erro: leva para a tela do código.
export function useEnvioAuth() {
  const navegar = useNavigate()
  const { iniciarSessao } = useAuth()
  const [erro, setErro] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  async function enviar(chamada, { email } = {}) {
    setErro(null)
    setOcupado(true)
    try {
      const resposta = await chamada()
      if (resposta?.access_token) {
        iniciarSessao(resposta)
        navegar('/painel', { replace: true })
      } else {
        // Conta criada: o acesso só vem depois do código que foi para o e-mail
        navegar('/confirmar-email', { replace: true, state: { email: resposta.email } })
      }
    } catch (falha) {
      if (falha.codigo === 'EMAIL_NOT_VERIFIED' && email) {
        navegar('/confirmar-email', { replace: true, state: { email, aviso: falha.message } })
        return
      }
      setErro(falha.message)
    } finally {
      setOcupado(false)
    }
  }

  return { erro, ocupado, enviar, mostrarErro: setErro }
}
