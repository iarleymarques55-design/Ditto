import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import EstadoVazio from '../../../components/ui/EstadoVazio.jsx'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import FluxoTabela from '../components/FluxoTabela.jsx'
import { useFluxos } from '../hooks/useFluxos.js'

function FluxosPage() {
  useTituloPagina('Tarefas')
  const consulta = useFluxos()

  return (
    <>
      <h1 className="font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">Tarefas gravadas</h1>
      <div className="mt-6">
        <EstadoConsulta consulta={consulta}>
          {(fluxos) =>
            fluxos.length > 0 ? (
              <FluxoTabela fluxos={fluxos} />
            ) : (
              <EstadoVazio titulo="Nenhuma tarefa gravada ainda.">Use o botão Gravar tarefa para trazer a primeira. Ela aparece aqui para você revisar.</EstadoVazio>
            )
          }
        </EstadoConsulta>
      </div>
    </>
  )
}

export default FluxosPage
