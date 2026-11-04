import { useState } from 'react'
import { formatarDiaCurto } from '../../../lib/datas.js'
import { editarPasso } from '../api.js'

function PassoItem({ fluxoId, passo, aoMudar }) {
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function editar(campos) {
    setEnviando(true)
    setErro(null)
    try {
      await editarPasso(fluxoId, passo.id, campos)
      aoMudar()
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <li className="grid grid-cols-[24px_minmax(0,1fr)] gap-x-2 border-t border-dashed border-tinta-media px-1 py-3">
      <span className="text-[16px] tabular-nums">{passo.posicao}</span>
      <div className="min-w-0">
        <p className="text-[17px] leading-snug break-words">{passo.intencao}</p>
        <div className="font-sans [text-shadow:none]">
          <p className="mt-1 text-[13.5px] text-grafite">Confere: {passo.posCondicao}</p>
          {passo.usaAcesso && <p className="mt-0.5 text-[13.5px] text-grafite">Usa o acesso salvo do portal</p>}

          {/* Abrir uma página não muda nada no portal: a pergunta só faz sentido nas ações */}
          {passo.acao !== 'navigate' && (
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13.5px] text-navy">
            <label className="flex min-h-8 cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                className="size-4 accent-rec-texto"
                checked={passo.irreversivel}
                disabled={enviando}
                onChange={(evento) => editar({ irreversivel: evento.target.checked })}
              />
              Não tem volta
            </label>
            {passo.irreversivel && (
              <label className="flex min-h-8 cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  className="size-4 accent-rec-texto"
                  checked={passo.autoConfirma}
                  disabled={enviando}
                  onChange={(evento) => editar({ autoConfirma: evento.target.checked })}
                />
                Seguir sem me perguntar
              </label>
            )}
          </div>
          )}

          {passo.reparo && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
              <span className="text-[13.5px] break-words text-navy">Novo caminho: {passo.reparo.caminho}</span>
              <span className="inline-block -rotate-3 rounded-[2px] border-[1.5px] border-ink px-1.5 py-px text-[12.5px] font-medium text-ink">
                reparado em {formatarDiaCurto(passo.reparo.em)}
              </span>
            </div>
          )}
          {erro && (
            <p role="alert" className="mt-1 text-[13.5px] font-medium text-rec-texto">
              {erro}
            </p>
          )}
        </div>
      </div>
    </li>
  )
}

export default PassoItem
