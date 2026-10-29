import { Link } from 'react-router'
import Logo from '../components/landing/Logo.jsx'

function Painel() {
  return (
    <main className="shell flex min-h-screen flex-col items-start justify-center gap-5 py-16">
      <Logo />
      <h1 className="font-display text-[34px] leading-tight font-bold text-navy">Painel em construção</h1>
      <Link to="/" className="inline-flex min-h-11 items-center text-[15px] font-medium text-ink hover:underline">
        Voltar para a página inicial
      </Link>
    </main>
  )
}

export default Painel
