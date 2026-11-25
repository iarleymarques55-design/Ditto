import { Suspense, lazy } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router'
import { AuthProvider, CadastroPage, ConfirmarEmailPage, LoginPage } from '../features/auth/index.js'
import Home from '../pages/Home.jsx'
import NaoEncontradoPage from '../pages/NaoEncontradoPage.jsx'
import PoliticaPrivacidadePage from '../pages/PoliticaPrivacidadePage.jsx'
import RotaProtegida from './RotaProtegida.jsx'

const Painel = lazy(() => import('../pages/Painel.jsx'))

function AppRouter() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Home />}>
            <Route path="entrar" element={<LoginPage />} />
            <Route path="criar-conta" element={<CadastroPage />} />
            <Route path="confirmar-email" element={<ConfirmarEmailPage />} />
          </Route>
          <Route path="/privacidade" element={<PoliticaPrivacidadePage />} />
          <Route element={<RotaProtegida />}>
            <Route
              path="/painel/*"
              element={
                <Suspense fallback={<div className="min-h-dvh bg-mesa" />}>
                  <Painel />
                </Suspense>
              }
            />
          </Route>
          <Route path="*" element={<NaoEncontradoPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default AppRouter
