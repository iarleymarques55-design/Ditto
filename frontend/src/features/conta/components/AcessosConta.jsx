import { useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import { formatarQuando } from '../../../lib/datas.js'
import { useConsulta } from '../../../lib/useConsulta.js'
import { apagarAcesso, listarAcessos } from '../api.js'
import { classeTitulo } from './campos.js'

function AcessosConta() {
  const consulta = useConsulta(listarAcessos)
  const [erro, setErro] = useState(null)

  async function apagar({ id, domain: dominio }) {
    // oxlint-disable-next-line no-alert -- confirmação simples: dá para salvar o acesso de novo na página da tarefa
    if (!window.confirm(`Apagar o acesso a ${dominio}? As tarefas que fazem login nesse portal param de rodar até você salvar de novo.`)) return
    setErro(null)
    try {
      await apagarAcesso(id)
      consulta.recarregar()
    } catch (falha) {
      setErro(falha.message)
    }
  }

  return (
    <section aria-labelledby="acessos-titulo">
      <h2 id="acessos-titulo" className={classeTitulo}>
        Acessos aos portais
      </h2>
      <p className="mt-1 max-w-[56ch] text-[14.5px]">
        Usuários e senhas ficam cifrados e nunca voltam para a tela. Para trocar um deles, vá à página da tarefa.
      </p>
      <div className="mt-2 max-w-[560px]">
        <EstadoConsulta consulta={consulta}>
          {(acessos) =>
            acessos.length === 0 ? (
              <p className="py-2 text-[15px] text-navy">Nenhum acesso salvo.</p>
            ) : (
              <ul className="border-t border-pauta">
                {acessos.map((acesso) => (
                  <li key={acesso.id} className="flex flex-wrap items-center justify-between gap-x-4 border-b border-pauta py-1.5">
                    <div className="min-w-0">
                      <p className="text-[15px] font-medium break-all text-navy">{acesso.domain}</p>
                      <p className="text-[13.5px]">Salvo {formatarQuando(acesso.updated_at)}</p>
                    </div>
                    <Botao variante="discreto" aria-label={`Apagar o acesso a ${acesso.domain}`} onClick={() => apagar(acesso)}>
                      Apagar
                    </Botao>
                  </li>
                ))}
              </ul>
            )
          }
        </EstadoConsulta>
        {erro && (
          <p role="alert" className="mt-1 text-[14px] font-medium text-rec-texto">
            {erro}
          </p>
        )}
      </div>
    </section>
  )
}

export default AcessosConta
