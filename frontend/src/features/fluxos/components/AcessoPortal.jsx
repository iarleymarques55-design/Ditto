import { useId, useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import { salvarAcesso } from '../api.js'

const classeCampo = 'mt-1 min-h-11 w-full rounded-[2px] border border-grafite/60 bg-papel-folha px-3 text-[15px] text-navy'

// O usuário e a senha só vão: a API nunca devolve esses valores, então a tela nunca os mostra de volta.
function AcessoPortal({ dominios, precisaAcesso, aoMudar }) {
  const [editando, setEditando] = useState(precisaAcesso)
  const [dominio, setDominio] = useState(dominios[0] ?? '')
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const idDominio = useId()
  const idUsuario = useId()
  const idSenha = useId()

  async function salvar(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro(null)
    try {
      await salvarAcesso({ dominio, usuario, senha })
      setUsuario('')
      setSenha('')
      setEditando(false)
      aoMudar()
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  if (!editando) {
    return (
      <div>
        <p className="text-[15px] font-medium text-navy">Acesso salvo com criptografia.</p>
        <Botao variante="discreto" className="mt-1" onClick={() => setEditando(true)}>
          Trocar usuário e senha
        </Botao>
      </div>
    )
  }

  return (
    <form onSubmit={salvar} className="space-y-3" autoComplete="off">
      <p className="text-[14.5px]">
        Esta tarefa faz login no portal. A senha fica cifrada e não é enviada para a IA.
      </p>
      {dominios.length > 1 && (
        <div>
          <label htmlFor={idDominio} className="text-[14px] font-medium text-navy">
            Portal
          </label>
          <select id={idDominio} value={dominio} onChange={(evento) => setDominio(evento.target.value)} className={classeCampo}>
            {dominios.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </div>
      )}
      <div>
        <label htmlFor={idUsuario} className="text-[14px] font-medium text-navy">
          Usuário no portal
        </label>
        <input
          id={idUsuario}
          value={usuario}
          onChange={(evento) => setUsuario(evento.target.value)}
          autoComplete="off"
          className={classeCampo}
        />
      </div>
      <div>
        <label htmlFor={idSenha} className="text-[14px] font-medium text-navy">
          Senha no portal
        </label>
        <input
          id={idSenha}
          type="password"
          required
          value={senha}
          onChange={(evento) => setSenha(evento.target.value)}
          autoComplete="new-password"
          className={classeCampo}
        />
      </div>
      {erro && (
        <p role="alert" className="text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
      <Botao type="submit" variante="contorno" disabled={enviando}>
        Salvar acesso
      </Botao>
    </form>
  )
}

export default AcessoPortal
