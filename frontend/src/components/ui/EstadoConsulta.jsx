import Botao from './Botao.jsx'
import Carregando from './Carregando.jsx'
import EstadoVazio from './EstadoVazio.jsx'

// Cuida do carregamento e do erro de uma consulta; os dados chegam em `children`.
// `paginaInteira`: a consulta é a página toda, então a mensagem de erro precisa ser o título dela.
function EstadoConsulta({ consulta, paginaInteira = false, children }) {
  if (consulta.carregando) return <Carregando />

  if (consulta.erro) {
    return (
      <EstadoVazio
        titulo="Não deu para abrir esta página."
        comoTitulo={paginaInteira}
        acao={
          <Botao variante="contorno" onClick={consulta.recarregar}>
            Tentar de novo
          </Botao>
        }
      >
        {consulta.erro.message}
      </EstadoVazio>
    )
  }

  return children(consulta.dados)
}

export default EstadoConsulta
