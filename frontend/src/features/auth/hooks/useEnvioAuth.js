import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from './useAuth.js'

// Estado comum dos dois formulários: envio em andamento, erro e destino depois do sucesso.
export function useEnvioAuth() {
  const navegar = useNavigate()
  const { iniciarSessao } = useAuth()
  const [erro, setErro] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  async function enviar(chamada) {
    setErro(null)
    setOcupado(true)
    try {
      iniciarSessao(await chamada())
      navegar('/painel', { replace: true })
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setOcupado(false)
    }
  }

  return { erro, ocupado, enviar, mostrarErro: setErro }
}
