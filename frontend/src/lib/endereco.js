// Aceita "portal.gov.br" ou "https://portal.gov.br/x" e devolve o endereço completo, ou null.
export function normalizarEndereco(texto) {
  const limpo = texto.trim()
  const comProtocolo = /^[a-z][a-z0-9+.-]*:\/\//i.test(limpo) ? limpo : `https://${limpo}`
  try {
    const url = new URL(comProtocolo)
    const protocoloValido = ['http:', 'https:'].includes(url.protocol)
    const hostValido = url.hostname.includes('.') || url.hostname === 'localhost'
    return protocoloValido && hostValido ? url.href : null
  } catch {
    return null
  }
}
