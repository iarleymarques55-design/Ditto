// Monta a extensão do Ditto já configurada para este painel, pronta para virar o .zip que o
// painel oferece em "Extensão". Roda no build da imagem (veja o Dockerfile):
//
//   node scripts/empacotar-extensao.mjs <pasta da extensão> <pasta de saída>
//
// Lê três variáveis, as mesmas do serviço do painel:
//   VITE_API_URL   endereço da API          (https://api.exemplo.com/api/v1)
//   VITE_RELE_URL  endereço do worker       (wss://worker.exemplo.com/extension)
//   PAINEL_URL     endereço deste painel    (https://painel.exemplo.com)
//
// Sem alguma delas, não monta nada e avisa: o painel mostra que o download não está disponível.

import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const LOCAIS = new Set(['localhost', '127.0.0.1'])

export class ConfiguracaoInvalida extends Error {}

function endereco(nome, valor, protocolosSeguros, protocolosLocais) {
  if (!valor) throw new ConfiguracaoInvalida(`${nome} não foi informado.`)
  let url
  try {
    url = new URL(valor)
  } catch {
    throw new ConfiguracaoInvalida(`${nome} não é um endereço válido: ${valor}`)
  }
  const local = LOCAIS.has(url.hostname)
  const aceitos = local ? [...protocolosSeguros, ...protocolosLocais] : protocolosSeguros
  if (!aceitos.includes(url.protocol)) {
    // Fora do computador local, tudo vai criptografado: a conexão leva o token da conta
    throw new ConfiguracaoInvalida(`${nome} precisa começar com ${protocolosSeguros.join(' ou ')}: ${valor}`)
  }
  return url
}

export function lerConfiguracao(ambiente) {
  const api = endereco('VITE_API_URL', ambiente.VITE_API_URL, ['https:'], ['http:'])
  const rele = endereco('VITE_RELE_URL', ambiente.VITE_RELE_URL, ['wss:'], ['ws:'])
  const painel = endereco('PAINEL_URL', ambiente.PAINEL_URL, ['https:'], ['http:'])
  return {
    apiUrl: api.href.replace(/\/$/, ''),
    releUrl: rele.href,
    // O Chrome só aceita a origem (protocolo, endereço e porta) na lista de páginas
    painelOrigem: painel.origin,
  }
}

export function configurarManifesto(texto, { painelOrigem }) {
  const manifesto = JSON.parse(texto)
  const ponte = manifesto.content_scripts?.find((script) => script.js?.includes('bridge.js'))
  if (!ponte) throw new ConfiguracaoInvalida('O manifest.json não tem a ponte com o painel (bridge.js).')
  // Só o painel deste Ditto conversa com a extensão baixada dele
  ponte.matches = [`${painelOrigem}/*`]
  return `${JSON.stringify(manifesto, null, 2)}\n`
}

export function configurarConfig(texto, { releUrl, apiUrl }) {
  const trocas = [
    [/^const RELE_URL = .*$/m, `const RELE_URL = ${JSON.stringify(releUrl)}`],
    [/^const API_URLS = .*$/m, `const API_URLS = ${JSON.stringify([apiUrl])}`],
  ]
  let resultado = texto
  for (const [linha, nova] of trocas) {
    if (!linha.test(resultado)) throw new ConfiguracaoInvalida(`O config.js mudou: não achei ${linha}.`)
    resultado = resultado.replace(linha, nova)
  }
  return resultado
}

export async function empacotar(origem, saida, ambiente) {
  const configuracao = lerConfiguracao(ambiente)
  const destino = path.join(saida, 'ditto-extensao')
  await rm(destino, { recursive: true, force: true })
  await mkdir(saida, { recursive: true })
  // README e arquivos de desenvolvimento ficam de fora: quem baixa só precisa do que o Chrome lê
  await cp(origem, destino, {
    recursive: true,
    filter: (arquivo) => !/(README\.md|\.DS_Store)$/.test(arquivo),
  })

  const manifesto = path.join(destino, 'manifest.json')
  await writeFile(manifesto, configurarManifesto(await readFile(manifesto, 'utf8'), configuracao))
  const config = path.join(destino, 'config.js')
  await writeFile(config, configurarConfig(await readFile(config, 'utf8'), configuracao))
  return { destino, ...configuracao }
}

const executadoDireto = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])
if (executadoDireto) {
  const [origem, saida] = process.argv.slice(2)
  try {
    const { destino, painelOrigem } = await empacotar(origem, saida, process.env)
    console.log(`Extensão configurada para ${painelOrigem} em ${destino}`)
  } catch (erro) {
    if (!(erro instanceof ConfiguracaoInvalida)) throw erro
    // Não derruba o build do painel: ele sobe e a página "Extensão" avisa que falta configurar
    console.warn(`AVISO: a extensão não foi montada para download. ${erro.message}`)
    process.exitCode = 0
  }
}
