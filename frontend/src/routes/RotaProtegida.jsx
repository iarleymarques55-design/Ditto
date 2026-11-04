import { Navigate, Outlet } from 'react-router'
import { useAuth } from '../features/auth/index.js'

function RotaProtegida() {
  const { usuario, carregando } = useAuth()

  // Enquanto confere o token, não mostra o painel nem manda para o login
  if (carregando) return <div className="min-h-dvh bg-mesa" />
  if (!usuario) return <Navigate to="/entrar" replace />
  return <Outlet />
}

export default RotaProtegida
