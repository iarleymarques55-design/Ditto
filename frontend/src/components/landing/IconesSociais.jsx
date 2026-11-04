// O lucide-react não tem ícones de marcas: estes são os desenhos oficiais simplificados.
function IconeBase({ className, children }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      {children}
    </svg>
  )
}

export function IconeGithub({ className }) {
  return (
    <IconeBase className={className}>
      <path d="M12 .3a12 12 0 0 0-3.8 23.38c.6.12.83-.26.83-.57l-.01-2.24c-3.34.73-4.04-1.42-4.04-1.42-.55-1.39-1.33-1.76-1.33-1.76-1.09-.74.08-.73.08-.73 1.2.09 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.5 1 .1-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.13-.3-.54-1.52.12-3.18 0 0 1-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.28-1.55 3.29-1.23 3.29-1.23.66 1.66.25 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.48 5.92.43.37.81 1.1.81 2.22l-.01 3.29c0 .32.22.69.83.57A12 12 0 0 0 12 .3Z" />
    </IconeBase>
  )
}

export function IconeLinkedin({ className }) {
  return (
    <IconeBase className={className}>
      <path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM2.82 9.75h4.32V21H2.82V9.75Zm7.03 0h4.14v1.54h.06c.58-1.09 1.98-2.24 4.08-2.24 4.36 0 5.17 2.87 5.17 6.6V21h-4.31v-5.05c0-1.2-.02-2.75-1.68-2.75-1.68 0-1.94 1.31-1.94 2.66V21h-4.32V9.75Z" />
    </IconeBase>
  )
}

export function IconeYoutube({ className }) {
  return (
    <IconeBase className={className}>
      <path d="M23.5 6.2a3 3 0 0 0-2.12-2.13C19.5 3.55 12 3.55 12 3.55s-7.5 0-9.38.52A3 3 0 0 0 .5 6.2 31.4 31.4 0 0 0 0 12a31.4 31.4 0 0 0 .5 5.8 3 3 0 0 0 2.12 2.13c1.88.52 9.38.52 9.38.52s7.5 0 9.38-.52a3 3 0 0 0 2.12-2.13A31.4 31.4 0 0 0 24 12a31.4 31.4 0 0 0-.5-5.8ZM9.6 15.6V8.4l6.27 3.6-6.27 3.6Z" />
    </IconeBase>
  )
}
