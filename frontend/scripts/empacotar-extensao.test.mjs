// Roda com: node --test scripts/
import assert from 'node:assert/strict'
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { ConfiguracaoInvalida, empacotar, lerConfiguracao } from './empacotar-extensao.mjs'

const EXTENSAO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../extension')

const PUBLICADO = {
  VITE_API_URL: 'https://api.exemplo.com/api/v1',
  VITE_RELE_URL: 'wss://worker.exemplo.com/extension',
  PAINEL_URL: 'https://painel.exemplo.com/',
}

async function comPasta(fazer) {
  const pasta = await mkdtemp(path.join(tmpdir(), 'ditto-extensao-'))
  try {
    return await fazer(pasta)
  } finally {
    await rm(pasta, { recursive: true, force: true })
  }
}

test('a extensão baixada fala só com o painel, a API e o worker deste Ditto', () =>
  comPasta(async (saida) => {
    const { destino } = await empacotar(EXTENSAO, saida, PUBLICADO)

    const manifesto = JSON.parse(await readFile(path.join(destino, 'manifest.json'), 'utf8'))
    const ponte = manifesto.content_scripts.find((script) => script.js.includes('bridge.js'))
    assert.deepEqual(ponte.matches, ['https://painel.exemplo.com/*'])
    // O ID fixo vem junto: o worker reconhece a extensão de qualquer computador
    assert.ok(manifesto.key)

    const config = await readFile(path.join(destino, 'config.js'), 'utf8')
    assert.match(config, /const RELE_URL = "wss:\/\/worker\.exemplo\.com\/extension"/)
    assert.match(config, /const API_URLS = \["https:\/\/api\.exemplo\.com\/api\/v1"\]/)
    assert.doesNotMatch(config, /localhost/)
  }))

test('o README e os arquivos de desenvolvimento não vão no pacote', () =>
  comPasta(async (saida) => {
    const { destino } = await empacotar(EXTENSAO, saida, PUBLICADO)
    const arquivos = await readdir(destino)
    assert.ok(arquivos.includes('manifest.json'))
    assert.ok(!arquivos.includes('README.md'))
  }))

test('no computador local, ws:// e http:// são aceitos', () => {
  const local = lerConfiguracao({
    VITE_API_URL: 'http://localhost:8000/api/v1',
    VITE_RELE_URL: 'ws://127.0.0.1:8765/extension',
    PAINEL_URL: 'http://localhost:5173',
  })
  assert.equal(local.painelOrigem, 'http://localhost:5173')
})

test('fora do computador local, endereço sem criptografia é recusado', () => {
  assert.throws(
    () => lerConfiguracao({ ...PUBLICADO, VITE_RELE_URL: 'ws://worker.exemplo.com/extension' }),
    ConfiguracaoInvalida,
  )
  assert.throws(() => lerConfiguracao({ ...PUBLICADO, PAINEL_URL: 'http://painel.exemplo.com' }), ConfiguracaoInvalida)
})

test('sem alguma variável, não monta nada', () => {
  assert.throws(() => lerConfiguracao({ ...PUBLICADO, VITE_RELE_URL: '' }), ConfiguracaoInvalida)
})

test('valores com aspas não quebram o config.js', () =>
  comPasta(async (saida) => {
    const { destino } = await empacotar(EXTENSAO, saida, {
      ...PUBLICADO,
      VITE_API_URL: "https://api.exemplo.com/api/v1?x='1'",
    })
    const config = await readFile(path.join(destino, 'config.js'), 'utf8')
    // Nenhuma aspa solta encerra a string antes da hora: a lista continua sendo um JSON válido
    const lista = JSON.parse(config.match(/^const API_URLS = (.*)$/m)[1])
    assert.equal(lista.length, 1)
    assert.ok(lista[0].startsWith('https://api.exemplo.com/api/v1?x='))
  }))
