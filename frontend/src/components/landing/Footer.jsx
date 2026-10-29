import Logo from './Logo.jsx'
import { navLinks } from './navLinks.js'

function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="shell flex flex-col gap-6 pt-8 pb-14 md:flex-row md:items-center md:justify-between">
        <Logo />
        <nav aria-label="Rodapé">
          <ul className="flex flex-wrap gap-x-11 text-[13px] text-navy">
            {navLinks.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="inline-flex min-h-11 items-center hover:text-ink">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <p className="text-[11px] leading-[1.6] text-muted md:text-right">
          Feito com cuidado por uma equipe pequena
          <br />
          que acredita em automações melhores.
        </p>
      </div>
    </footer>
  )
}

export default Footer
