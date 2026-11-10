// Dados da demo do hero. Tudo é simulado no front: sem IA e sem rede.

export const PORTAL_URL = 'portal.fornecedor.exemplo/relatorios'
export const MES = '09/2026'
const PASTA = 'relatorios/09-2026'
const TOTAL_LOJAS = 25

export const PASSO_MS = 350
export const TENTATIVA_MS = 600
export const ESPERA_AUTOPLAY_MS = 700

export const MATRIZ = {
  cabecalho: 'Matriz gravada por Carla em 12/08',
  titulo: 'Relatório mensal por loja',
  carimbo: 'reparado em 05/10',
  caminhoReparado: 'Ações ▾ › Baixar como PDF',
}

export const PASSOS = [
  'Abrir a página de relatórios',
  'Escolher a loja',
  'Informar o mês',
  'Gerar o relatório',
  'Esperar a tabela carregar',
  'Exportar em PDF',
  'Salvar na pasta do mês',
]

export const PASSO_EXPORTAR = 6

// tempo = segundos de uma cópia sem reparo
export const LOJAS = [
  { numero: 1, nome: 'Loja 01 - Shopping Norte', tempo: 11 },
  { numero: 2, nome: 'Loja 02 - Aldeota', tempo: 10 },
  { numero: 3, nome: 'Loja 03 - Messejana', tempo: 12 },
  { numero: 4, nome: 'Loja 04 - Parangaba', tempo: 10 },
  { numero: 5, nome: 'Loja 05 - Benfica', tempo: 11 },
  { numero: 6, nome: 'Loja 06 - Papicu', tempo: 13 },
  { numero: 7, nome: 'Loja 07 - Centro', tempo: 10 },
]

// Segundos a mais na cópia em que o Ditto precisa reparar o passo.
export const TEMPO_REPARO = 8

export const LINHAS_TABELA = [
  { pedido: '#48213', data: '03/09', valor: 'R$ 1.240,00' },
  { pedido: '#48377', data: '12/09', valor: 'R$ 986,50' },
  { pedido: '#48502', data: '26/09', valor: 'R$ 2.115,90' },
]

// Tipos de linha do registro: info, ok, falha, busca, achado
export const REGISTRO = {
  mudouLayout: 'o portal mudou de layout',
  exportouA: '✔ passo 6: Exportar PDF',
  caminhoReparado: '✔ passo 6: usando o caminho reparado',
}

// Passo 6 no layout B antes do reparo. efeito dispara a mudança visual junto com a linha.
export const TENTATIVAS = [
  { texto: 'passo 6: "Exportar o relatório em PDF"', tipo: 'info' },
  { texto: '✘ tentativa 1: botão gravado não encontrado', tipo: 'falha' },
  { texto: '✘ tentativa 2: elemento mais parecido = 41%', tipo: 'falha' },
  { texto: '⟳ tentativa 3: perguntando à IA onde foi parar...', tipo: 'busca' },
  { texto: '→ abrir "Ações ▾" e clicar em "Baixar como PDF"', tipo: 'achado', efeito: 'abrirMenu' },
  { texto: '✔ PDF baixado. Novo caminho salvo.', tipo: 'ok', efeito: 'reparar' },
]

export function linhaLoja(loja) {
  return `[${String(loja.numero).padStart(2, '0')}/${TOTAL_LOJAS}] ${loja.nome}`
}

export function linhaSalvo(loja, segundos) {
  return `✔ salvo em ${PASTA}/loja-${String(loja.numero).padStart(2, '0')}.pdf  (${segundos} s)`
}
