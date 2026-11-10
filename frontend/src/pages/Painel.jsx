import { Route, Routes } from 'react-router'
import LayoutPainel from '../components/layout/LayoutPainel.jsx'
import Botao from '../components/ui/Botao.jsx'
import EstadoVazio from '../components/ui/EstadoVazio.jsx'
import { useAuth } from '../features/auth/index.js'
import { AtalhoConta, ContaPage } from '../features/conta/index.js'
import { DashboardPage } from '../features/dashboard/index.js'
import { ExecucaoDetalhePage, ExecucoesPage, NovaExecucaoPage } from '../features/execucoes/index.js'
import { FluxoDetalhePage, FluxosPage, GravarTarefa } from '../features/fluxos/index.js'
import { ReparosPage, usePedidos } from '../features/reparos/index.js'

function PaginaNaoEncontrada() {
  return (
    <EstadoVazio titulo="Esta folha não está no fichário." comoTitulo acao={<Botao para="/painel">Voltar para a mesa</Botao>}>
      O endereço pode estar errado ou a página pode ter mudado de lugar.
    </EstadoVazio>
  )
}

// Tudo o que vem depois do login. Fica em um arquivo separado para a landing não carregar o painel.
function Painel() {
  const { dados: pedidos } = usePedidos()
  const { sair } = useAuth()

  return (
    <Routes>
      <Route
        element={
          <LayoutPainel
            pedidosPendentes={pedidos?.length ?? 0}
            perfil={<AtalhoConta />}
            acaoPrincipal={<GravarTarefa />}
            aoSair={sair}
          />
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="tarefas" element={<FluxosPage />} />
        <Route path="tarefas/:id" element={<FluxoDetalhePage />} />
        <Route path="execucoes" element={<ExecucoesPage />} />
        <Route path="execucoes/nova" element={<NovaExecucaoPage />} />
        <Route path="execucoes/:id" element={<ExecucaoDetalhePage />} />
        <Route path="reparos" element={<ReparosPage />} />
        <Route path="conta" element={<ContaPage />} />
        <Route path="*" element={<PaginaNaoEncontrada />} />
      </Route>
    </Routes>
  )
}

export default Painel
