import { useState } from 'react'
import { useAuth } from '../../auth/index.js'
import { salvarConta } from '../api.js'
import { classeTitulo } from './campos.js'

function AvisosConta() {
  const { usuario, atualizarUsuario } = useAuth()
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function alternar(evento) {
    setEnviando(true)
    setErro(null)
    try {
      atualizarUsuario(await salvarConta({ alertas: evento.target.checked }))
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section aria-labelledby="avisos-titulo">
      <h2 id="avisos-titulo" className={classeTitulo}>
        Avisos
      </h2>
      <label className="mt-2 flex min-h-11 max-w-[56ch] cursor-pointer items-start gap-3 py-1.5 text-[15px] text-navy">
        <input type="checkbox" className="mt-1 size-[18px] shrink-0 accent-ink" checked={usuario.email_alerts} disabled={enviando} onChange={alternar} />
        <span>
          Me avisar por e-mail quando uma tarefa parar esperando uma decisão ou terminar com problemas.
          <span className="mt-0.5 block text-[13.5px] text-grafite">Com isso desligado, os pedidos continuam aparecendo no painel.</span>
        </span>
      </label>
      {erro && (
        <p role="alert" className="mt-1 text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </section>
  )
}

export default AvisosConta
