import { useState } from 'react'
import { Link } from 'react-router'
import { Menu, X } from 'lucide-react'
import Logo from './Logo.jsx'
import RecordIcon from './RecordIcon.jsx'
import { navLinks } from './navLinks.js'

function Navbar() {
  const [menuAberto, setMenuAberto] = useState(false)

  return (
    <header className="border-b border-line bg-hero">
      <div className="shell flex h-[72px] items-center justify-between gap-4">
        <Logo />

        <nav aria-label="Principal" className="hidden md:block">
          <ul className="flex items-center gap-11 text-[13px] text-navy">
            {navLinks.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="inline-flex min-h-11 items-center hover:text-ink">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-1">
          <Link
            to="/painel"
            className="inline-flex h-11 items-center gap-2.5 rounded-full bg-rec pr-6 pl-4 text-[14px] font-medium text-white hover:brightness-95"
          >
            <RecordIcon />
            Gravar
          </Link>
          <button
            type="button"
            onClick={() => setMenuAberto((aberto) => !aberto)}
            aria-expanded={menuAberto}
            aria-controls="menu-celular"
            aria-label={menuAberto ? 'Fechar menu' : 'Abrir menu'}
            className="inline-flex size-11 items-center justify-center rounded-full text-navy md:hidden"
          >
            {menuAberto ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      {menuAberto && (
        <nav id="menu-celular" aria-label="Principal" className="border-t border-line md:hidden">
          <ul className="shell py-2 text-[15px] text-navy">
            {navLinks.map((link) => (
              <li key={link.href}>
                <a href={link.href} onClick={() => setMenuAberto(false)} className="flex min-h-11 items-center">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  )
}

export default Navbar
