const ORIGENS = {
  column: 'coluna da planilha',
  previous_month: 'sempre o mês anterior',
  today: 'sempre a data de hoje',
}

export function mapearVariavel(variavel) {
  return {
    id: variavel.id,
    nome: variavel.name,
    rotulo: variavel.label,
    exemplo: variavel.example,
    fonte: variavel.source,
    origem: ORIGENS[variavel.source],
    coluna: variavel.source === 'column',
    confirmada: variavel.status === 'confirmed',
  }
}
