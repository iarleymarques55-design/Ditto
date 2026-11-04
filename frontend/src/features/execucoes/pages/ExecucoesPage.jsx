import { useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import EstadoVazio from '../../../components/ui/EstadoVazio.jsx'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import TabelaExecucoes from '../components/TabelaExecucoes.jsx'
import { useExecucoes } from '../hooks/useExecucoes.js'

const FILTROS = [
  { id: 'todas', rotulo: 'Todas', aceita: () => true },
  { id: 'abertas', rotulo: 'Em andamento', aceita: (situacao) => situacao === 'rodando' || situacao === 'espera' },
  { id: 'concluidas', rotulo: 'Concluídas', aceita: (situacao) => situacao === 'concluida' },
  { id: 'problemas', rotulo: 'Com problemas', aceita: (situacao) => situacao === 'parcial' || situacao === 'falhou' },
]

function ExecucoesPage() {
  useTituloPagina('Execuções')
  const consulta = useExecucoes()
  const [filtro, setFiltro] = useState('todas')
  const { aceita } = FILTROS.find(({ id }) => id === filtro)

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">Execuções</h1>
        <Botao para="/painel/execucoes/nova">Nova execução</Botao>
      </div>

      <div className="mt-6">
        <EstadoConsulta consulta={consulta}>
          {(execucoes) => {
            if (execucoes.length === 0) {
              return <EstadoVazio titulo="Nenhuma execução ainda.">Quando uma tarefa rodar, o histórico aparece aqui.</EstadoVazio>
            }

            const visiveis = execucoes.filter((execucao) => aceita(execucao.situacao))
            return (
              <>
                <fieldset className="mb-6 flex flex-wrap gap-2">
                  <legend className="sr-only">Filtrar execuções</legend>
                  {FILTROS.map(({ id, rotulo }) => (
                    <button
                      key={id}
                      type="button"
                      aria-pressed={filtro === id}
                      onClick={() => setFiltro(id)}
                      className={`inline-flex min-h-10 items-center rounded-full border px-3.5 text-[14px] font-medium ${
                        filtro === id ? 'border-ink bg-ink text-white' : 'border-tinta-media text-navy hover:bg-tinta-clara'
                      }`}
                    >
                      {rotulo}
                    </button>
                  ))}
                </fieldset>
                {visiveis.length > 0 ? (
                  <TabelaExecucoes execucoes={visiveis} legenda="Execuções, da mais recente para a mais antiga" />
                ) : (
                  <EstadoVazio titulo="Nenhuma execução neste filtro." />
                )}
              </>
            )
          }}
        </EstadoConsulta>
      </div>
    </>
  )
}

export default ExecucoesPage
