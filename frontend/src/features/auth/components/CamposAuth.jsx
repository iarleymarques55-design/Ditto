import { useId, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

const classeCampo =
  'h-11 w-full rounded-[10px] border border-tinta-media bg-card px-3.5 text-[15px] text-navy outline-none placeholder:text-muted focus:border-ink focus:ring-4 focus:ring-ink/15 motion-safe:transition-shadow'

const classeRotulo = 'text-[14px] font-medium text-navy'

export function Campo({ rotulo, ...props }) {
  const id = useId()

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={classeRotulo}>
        {rotulo}
      </label>
      <input id={id} required className={classeCampo} {...props} />
    </div>
  )
}

export function CampoSenha({ rotulo, ...props }) {
  const id = useId()
  const [visivel, setVisivel] = useState(false)
  const Icone = visivel ? Eye : EyeOff

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={classeRotulo}>
        {rotulo}
      </label>
      <div className="relative">
        <input id={id} required type={visivel ? 'text' : 'password'} className={`${classeCampo} pr-11`} {...props} />
        <button
          type="button"
          onClick={() => setVisivel(!visivel)}
          aria-label={visivel ? 'Esconder senha' : 'Mostrar senha'}
          aria-pressed={visivel}
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-[10px] text-body hover:text-navy"
        >
          <Icone aria-hidden="true" className="size-[18px]" />
        </button>
      </div>
    </div>
  )
}

export function BotaoEnviar({ ocupado, children }) {
  return (
    <button
      type="submit"
      disabled={ocupado}
      className="mt-1 h-11 rounded-[10px] bg-ink text-[15px] font-bold text-white hover:bg-navy disabled:opacity-60 motion-safe:transition-colors"
    >
      {ocupado ? 'Aguarde...' : children}
    </button>
  )
}

export function MensagemErro({ children }) {
  if (!children) return null

  return (
    <p role="alert" className="rounded-[10px] bg-rec/10 px-3.5 py-2.5 text-[14px] text-navy">
      {children}
    </p>
  )
}
