import { useEffect, useRef } from 'react'

// <dialog> nativo: prende o foco, deixa a página de trás inerte e devolve o foco ao fechar.
// Para escolher o campo que recebe o foco ao abrir, marque-o com data-foco-inicial.
function Modal({ idTitulo, aoFechar, className = '', children }) {
  const dialogo = useRef(null)

  useEffect(() => {
    const elemento = dialogo.current
    const overflowAnterior = document.body.style.overflow

    elemento.showModal()
    elemento.querySelector('[data-foco-inicial]')?.focus()
    document.body.style.overflow = 'hidden'

    return () => {
      elemento.close()
      document.body.style.overflow = overflowAnterior
    }
  }, [])

  return (
    // oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- clicar fora é atalho de mouse; no teclado o Esc faz o mesmo
    <dialog
      ref={dialogo}
      aria-labelledby={idTitulo}
      onCancel={(evento) => {
        evento.preventDefault()
        aoFechar()
      }}
      onMouseDown={(evento) => {
        // O clique no fundo chega com o próprio dialog como alvo
        if (evento.target === dialogo.current) aoFechar()
      }}
      className={`m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] overflow-y-auto backdrop:bg-navy/75 backdrop:backdrop-blur-md ${className}`}
    >
      {children}
    </dialog>
  )
}

export default Modal
