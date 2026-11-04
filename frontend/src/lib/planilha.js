// Leitura de CSV no navegador, só para conferir a planilha antes de enviar.
// Aceita vírgula ou ponto e vírgula (o Excel em português exporta com ponto e vírgula).

export const LIMITE_LINHAS = 500
export const LIMITE_BYTES = 5 * 1024 * 1024

function detectarSeparador(texto) {
  const primeiraLinha = texto.split(/\r?\n/, 1)[0]
  const pontoEVirgula = primeiraLinha.split(';').length
  const virgula = primeiraLinha.split(',').length
  return pontoEVirgula > virgula ? ';' : ','
}

function separarCampos(texto, separador) {
  const linhas = []
  let linha = []
  let campo = ''
  let entreAspas = false

  for (let indice = 0; indice < texto.length; indice += 1) {
    const caractere = texto[indice]

    if (entreAspas) {
      if (caractere === '"' && texto[indice + 1] === '"') {
        campo += '"'
        indice += 1
      } else if (caractere === '"') {
        entreAspas = false
      } else {
        campo += caractere
      }
    } else if (caractere === '"') {
      entreAspas = true
    } else if (caractere === separador) {
      linha.push(campo)
      campo = ''
    } else if (caractere === '\n') {
      linha.push(campo)
      linhas.push(linha)
      linha = []
      campo = ''
    } else if (caractere !== '\r') {
      campo += caractere
    }
  }

  linha.push(campo)
  linhas.push(linha)
  return linhas
}

// "Mês " vira "mes", para comparar com o nome da variável
function normalizarColuna(nome) {
  return nome
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
}

export function lerCsv(conteudo) {
  const texto = conteudo.replace(/^﻿/, '')
  const [cabecalho = [], ...resto] = separarCampos(texto, detectarSeparador(texto))
  const colunas = cabecalho.map(normalizarColuna)

  const linhas = resto
    .filter((campos) => campos.some((campo) => campo.trim() !== ''))
    .map((campos) => Object.fromEntries(colunas.map((coluna, indice) => [coluna, (campos[indice] ?? '').trim()])))

  return { colunas, linhas }
}
