import { useState } from 'react'
import Fita from '../../../components/landing/mesa/Fita.jsx'
import Botao from '../../../components/ui/Botao.jsx'
import { useAuth } from '../../auth/index.js'
import { enviarFoto, removerFoto } from '../api.js'
import Avatar from './Avatar.jsx'

const LIMITE_BYTES = 3 * 1024 * 1024

// O crachá da conta: a foto presa com fita, como um documento sobre a mesa.
function Cracha() {
  const { usuario, atualizarUsuario } = useAuth()
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function fazer(acao) {
    setEnviando(true)
    setErro(null)
    try {
      atualizarUsuario(await acao())
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  function escolher(arquivo) {
    if (arquivo.size > LIMITE_BYTES) {
      setErro('A foto passa de 3 MB. Escolha uma imagem menor.')
      return
    }
    fazer(() => enviarFoto(arquivo))
  }

  return (
    <section aria-labelledby="cracha-nome" className="folha relative px-6 pt-8 pb-6 lg:-rotate-[0.7deg]">
      <Fita className="-top-2.5 left-1/2 -translate-x-1/2 -rotate-2" />

      <Avatar
        usuario={usuario}
        className="mx-auto aspect-square w-full max-w-[220px] rounded-[2px] shadow-[1px_2px_3px_rgba(70,48,20,0.25)]"
        classeIniciais="text-[72px]"
      />

      <h2 id="cracha-nome" className="mt-5 text-center font-display text-[24px] leading-tight font-bold break-words text-navy">
        {usuario.name}
      </h2>
      <p className="mt-1 text-center text-[14.5px] break-all">{usuario.email}</p>
      <p className="mt-3 border-t border-dashed border-tinta-media pt-3 text-center text-[13.5px]">
        {usuario.has_password ? 'Entra com e-mail e senha' : 'Entra com a conta Google'}
      </p>

      <div className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
        <label className="inline-flex min-h-11 cursor-pointer items-center rounded-full border border-ink px-5 text-[14.5px] font-medium text-ink focus-within:outline-2 focus-within:outline-offset-3 focus-within:outline-ink hover:bg-tinta-clara">
          {enviando ? 'Enviando...' : usuario.avatar_id ? 'Trocar foto' : 'Colocar foto'}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            disabled={enviando}
            onChange={(evento) => {
              const [arquivo] = evento.target.files
              if (arquivo) escolher(arquivo)
              evento.target.value = ''
            }}
          />
        </label>
        {usuario.avatar_id && (
          <Botao variante="discreto" disabled={enviando} onClick={() => fazer(removerFoto)}>
            Remover
          </Botao>
        )}
      </div>
      <p className="mt-2 text-center text-[13px]">PNG, JPG ou WebP, até 3 MB</p>

      {erro && (
        <p role="alert" className="mt-2 text-center text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </section>
  )
}

export default Cracha
