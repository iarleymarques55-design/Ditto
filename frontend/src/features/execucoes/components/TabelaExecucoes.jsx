import { Link } from 'react-router'
import Tabela from '../../../components/ui/Tabela.jsx'
import { formatarDuracao, formatarQuando } from '../../../lib/datas.js'
import StatusExecucao from './StatusExecucao.jsx'

function TabelaExecucoes({ execucoes, legenda, mostrarTarefa = true }) {
  return (
    <Tabela legenda={legenda}>
      <thead>
        <tr>
          <th scope="col">{mostrarTarefa ? 'Tarefa' : 'Início'}</th>
          {mostrarTarefa && (
            <th scope="col" className="hidden md:table-cell">
              Início
            </th>
          )}
          <th scope="col">Cópias</th>
          <th scope="col" className="hidden lg:table-cell">
            Duração
          </th>
          <th scope="col">Situação</th>
        </tr>
      </thead>
      <tbody>
        {execucoes.map((execucao) => {
          const destino = `/painel/execucoes/${execucao.id}`
          const estiloLink = 'font-medium text-navy underline decoration-ink/40 underline-offset-[3px] hover:text-ink hover:decoration-ink'
          return (
            <tr key={execucao.id}>
              <td className="min-w-0">
                <Link to={destino} className={estiloLink}>
                  {mostrarTarefa ? execucao.fluxoNome : formatarQuando(execucao.inicio)}
                </Link>
                {mostrarTarefa && <span className="mt-0.5 block text-[13px] md:hidden">{formatarQuando(execucao.inicio)}</span>}
              </td>
              {mostrarTarefa && <td className="hidden whitespace-nowrap md:table-cell">{formatarQuando(execucao.inicio)}</td>}
              <td className="whitespace-nowrap tabular-nums">
                {execucao.concluidas} de {execucao.total}
              </td>
              <td className="hidden whitespace-nowrap tabular-nums lg:table-cell">{formatarDuracao(execucao.duracaoS)}</td>
              <td>
                <StatusExecucao situacao={execucao.situacao} />
              </td>
            </tr>
          )
        })}
      </tbody>
    </Tabela>
  )
}

export default TabelaExecucoes
