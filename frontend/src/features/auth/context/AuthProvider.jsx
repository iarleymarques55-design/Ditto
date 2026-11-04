import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import { EVENTO_SESSAO_ENCERRADA, apagarToken, lerToken, salvarToken } from '../../../lib/http.js'
import { buscarContaLogada } from '../api.js'

export const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [carregando, setCarregando] = useState(() => Boolean(lerToken()))

  // Quem já tinha entrado volta direto, desde que o token ainda valha
  useEffect(() => {
    if (!lerToken()) return undefined

    let ativo = true
    buscarContaLogada()
      .then((conta) => {
        if (ativo) setUsuario(conta)
      })
      .catch(() => {
        if (ativo) setUsuario(null)
      })
      .finally(() => {
        if (ativo) setCarregando(false)
      })
    return () => {
      ativo = false
    }
  }, [])

  useEffect(() => {
    const encerrar = () => setUsuario(null)
    window.addEventListener(EVENTO_SESSAO_ENCERRADA, encerrar)
    return () => window.removeEventListener(EVENTO_SESSAO_ENCERRADA, encerrar)
  }, [])

  const iniciarSessao = useCallback(({ access_token: token, user }) => {
    salvarToken(token)
    setUsuario(user)
  }, [])

  const sair = useCallback(() => {
    apagarToken()
    setUsuario(null)
  }, [])

  const valor = useMemo(
    () => ({ usuario, carregando, iniciarSessao, atualizarUsuario: setUsuario, sair }),
    [usuario, carregando, iniciarSessao, sair],
  )

  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>
}
