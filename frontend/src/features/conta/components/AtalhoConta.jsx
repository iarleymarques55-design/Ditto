import { Settings } from 'lucide-react'
import { Link } from 'react-router'
import { useAuth } from '../../auth/index.js'
import Avatar from './Avatar.jsx'

// No topo do painel: foto, nome e a engrenagem que leva para as configurações.
function AtalhoConta() {
  const { usuario } = useAuth()
  if (!usuario) return null

  return (
    <Link
      to="/painel/conta"
      aria-label={`Configurações da conta de ${usuario.name}`}
      title="Configurações da conta"
      className="group inline-flex min-h-11 min-w-0 items-center gap-2 rounded-full pr-1 text-[14px] text-grafite hover:text-ink"
    >
      <Avatar usuario={usuario} className="size-8 shrink-0 rounded-full" />
      <span className="max-w-[20ch] truncate">{usuario.name}</span>
      <Settings aria-hidden="true" className="size-[18px] shrink-0 motion-safe:transition-transform motion-safe:group-hover:rotate-45" />
    </Link>
  )
}

export default AtalhoConta
