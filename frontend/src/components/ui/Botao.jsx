import { Link } from 'react-router'

const VARIANTES = {
  primario: 'bg-ink text-white shadow-botao hover:brightness-110',
  contorno: 'border border-ink text-ink hover:bg-tinta-clara',
  discreto: 'text-navy underline decoration-ink decoration-[1.5px] underline-offset-4 hover:text-ink',
}

// Com `para` vira um link; sem ele, um botão.
function Botao({ para, variante = 'primario', className = '', children, ...props }) {
  const preenchimento = variante === 'discreto' ? 'px-1' : 'rounded-full px-5'
  const classes = `inline-flex min-h-11 items-center justify-center gap-2 text-[14.5px] font-medium whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50 ${preenchimento} ${VARIANTES[variante]} ${className}`

  if (para) {
    return (
      <Link to={para} className={classes} {...props}>
        {children}
      </Link>
    )
  }

  return (
    <button type="button" className={classes} {...props}>
      {children}
    </button>
  )
}

export default Botao
