import { useId } from 'react'
import { Link, useNavigate } from 'react-router'
import { X } from 'lucide-react'
import Logo from '../../../components/landing/Logo.jsx'
import Modal from '../../../components/ui/Modal.jsx'

// A landing continua por trás, desfocada: as duas telas são rotas filhas da página inicial.
function ModalAuth({ titulo, subtitulo, pergunta, trocarPara, trocarTexto, children }) {
  const navegar = useNavigate()
  const idTitulo = useId()
  const fechar = () => navegar('/')

  return (
    <Modal
      idTitulo={idTitulo}
      aoFechar={fechar}
      className="max-w-[420px] rounded-2xl bg-card shadow-[0_24px_64px_rgb(19_16_79/0.45)]"
    >
      <div className="relative px-6 pt-7 pb-6 sm:px-9">
        <button
          type="button"
          onClick={fechar}
          aria-label="Fechar"
          className="absolute top-2 right-2 flex size-11 items-center justify-center rounded-full text-body hover:bg-card-soft hover:text-navy motion-safe:transition-colors"
        >
          <X aria-hidden="true" className="size-4" />
        </button>

        <div className="flex justify-center">
          <Logo />
        </div>
        <h1 id={idTitulo} className="mt-3 text-center font-display text-[24px] leading-tight font-bold text-navy">
          {titulo}
        </h1>
        <p className="mt-2 mb-6 text-center text-[14px] text-body">{subtitulo}</p>

        {children}

        <p className="mt-5 text-center text-[14px] text-body">
          {pergunta}{' '}
          <Link
            to={trocarPara}
            replace
            className="inline-flex min-h-11 items-center font-medium text-ink underline-offset-2 hover:underline -my-3"
          >
            {trocarTexto}
          </Link>
        </p>
      </div>
    </Modal>
  )
}

export default ModalAuth
