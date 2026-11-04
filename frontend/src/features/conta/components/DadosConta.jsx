import { useId, useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import { useAuth } from '../../auth/index.js'
import { salvarConta } from '../api.js'
import { classeCampo, classeRotulo, classeTitulo } from './campos.js'

function DadosConta() {
  const { usuario, atualizarUsuario } = useAuth()
  const [nome, setNome] = useState(usuario.name)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const [salvo, setSalvo] = useState(false)
  const idNome = useId()
  const idEmail = useId()

  async function salvar(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro(null)
    setSalvo(false)
    try {
      atualizarUsuario(await salvarConta({ nome }))
      setSalvo(true)
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section aria-labelledby="dados-titulo">
      <h2 id="dados-titulo" className={classeTitulo}>
        Seus dados
      </h2>
      <form onSubmit={salvar} className="mt-3 max-w-[460px] space-y-3">
        <div>
          <label htmlFor={idNome} className={classeRotulo}>
            Nome
          </label>
          <input
            id={idNome}
            required
            maxLength={120}
            value={nome}
            onChange={(evento) => {
              setNome(evento.target.value)
              setSalvo(false)
            }}
            autoComplete="name"
            className={classeCampo}
          />
        </div>
        <div>
          <label htmlFor={idEmail} className={classeRotulo}>
            E-mail
          </label>
          <input id={idEmail} value={usuario.email} readOnly className={`${classeCampo} cursor-default bg-card-soft`} />
          <p className="mt-1 text-[13.5px]">É o seu acesso à conta, então não muda por aqui.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Botao type="submit" variante="contorno" disabled={enviando || nome.trim() === usuario.name}>
            Salvar nome
          </Botao>
          {salvo && (
            <p role="status" className="text-[14px] font-medium text-ok-texto">
              Nome salvo.
            </p>
          )}
        </div>
        {erro && (
          <p role="alert" className="text-[14px] font-medium text-rec-texto">
            {erro}
          </p>
        )}
      </form>
    </section>
  )
}

export default DadosConta
