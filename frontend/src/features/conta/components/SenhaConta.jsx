import { useId, useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import { useAuth } from '../../auth/index.js'
import { trocarSenha } from '../api.js'
import { classeCampo, classeRotulo, classeTitulo } from './campos.js'

const VAZIO = { atual: '', nova: '', repetida: '' }

function SenhaConta() {
  const { usuario, iniciarSessao } = useAuth()
  const [campos, setCampos] = useState(VAZIO)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const [salvo, setSalvo] = useState(false)
  const idAtual = useId()
  const idNova = useId()
  const idRepetida = useId()
  const temSenha = usuario.has_password

  const alterar = (chave) => (evento) => setCampos({ ...campos, [chave]: evento.target.value })

  async function salvar(evento) {
    evento.preventDefault()
    setSalvo(false)
    if (campos.nova !== campos.repetida) {
      setErro('As senhas novas não são iguais. Digite a mesma nos dois campos.')
      return
    }

    setEnviando(true)
    setErro(null)
    try {
      // A troca encerra os tokens antigos: a resposta traz um novo para esta sessão continuar
      iniciarSessao(await trocarSenha({ atual: campos.atual, nova: campos.nova }))
      setCampos(VAZIO)
      setSalvo(true)
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section aria-labelledby="senha-titulo">
      <h2 id="senha-titulo" className={classeTitulo}>
        {temSenha ? 'Trocar a senha' : 'Criar uma senha'}
      </h2>
      <p className="mt-1 max-w-[56ch] text-[14.5px]">
        {temSenha
          ? 'Ao trocar, as outras sessões abertas desta conta são encerradas.'
          : 'Sua conta entra pelo Google. Com uma senha, você também entra com o e-mail.'}
      </p>
      <form onSubmit={salvar} className="mt-3 max-w-[460px] space-y-3">
        {temSenha && (
          <div>
            <label htmlFor={idAtual} className={classeRotulo}>
              Senha atual
            </label>
            <input id={idAtual} type="password" required value={campos.atual} onChange={alterar('atual')} autoComplete="current-password" className={classeCampo} />
          </div>
        )}
        <div>
          <label htmlFor={idNova} className={classeRotulo}>
            Senha nova (mínimo 8 caracteres)
          </label>
          <input id={idNova} type="password" required minLength={8} maxLength={72} value={campos.nova} onChange={alterar('nova')} autoComplete="new-password" className={classeCampo} />
        </div>
        <div>
          <label htmlFor={idRepetida} className={classeRotulo}>
            Repita a senha nova
          </label>
          <input id={idRepetida} type="password" required minLength={8} maxLength={72} value={campos.repetida} onChange={alterar('repetida')} autoComplete="new-password" className={classeCampo} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Botao type="submit" variante="contorno" disabled={enviando}>
            {temSenha ? 'Trocar a senha' : 'Criar a senha'}
          </Botao>
          {salvo && (
            <p role="status" className="text-[14px] font-medium text-ok-texto">
              Senha salva.
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

export default SenhaConta
