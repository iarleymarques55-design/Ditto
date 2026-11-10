import { FileSpreadsheet } from 'lucide-react'
import { useId, useState } from 'react'
import { LIMITE_BYTES, LIMITE_LINHAS, lerCsv } from '../../../lib/planilha.js'

function validar({ colunas, linhas }, esperadas) {
  const faltando = esperadas.filter((coluna) => !colunas.includes(coluna))
  if (faltando.length > 0) {
    return `Faltam as colunas ${faltando.join(', ')}. A primeira linha da planilha precisa ter esses nomes.`
  }
  if (linhas.length === 0) return 'A planilha só tem o cabeçalho. Adicione ao menos uma linha.'
  if (linhas.length > LIMITE_LINHAS) return `A planilha tem ${linhas.length} linhas. O limite é ${LIMITE_LINHAS}.`
  return null
}

function extensaoDe(nome) {
  return nome.toLowerCase().split('.').pop()
}

// A bandeja de entrada da máquina. Confere o CSV aqui para o erro aparecer antes de enviar;
// o Excel é conferido pela API, que também valida o CSV de novo.
function UploadLote({ colunas, aoCarregar }) {
  const [erro, setErro] = useState(null)
  const [arrastando, setArrastando] = useState(false)
  const idDica = useId()

  async function lerArquivo(arquivo) {
    setErro(null)
    const extensao = extensaoDe(arquivo.name)
    if (!['csv', 'xlsx', 'xlsm'].includes(extensao)) {
      setErro('Envie a planilha em .csv ou .xlsx.')
      return
    }
    if (arquivo.size > LIMITE_BYTES) {
      setErro('O arquivo passa de 5 MB. Divida a planilha em partes menores.')
      return
    }

    if (extensao !== 'csv') {
      aoCarregar({ nome: arquivo.name, arquivo, linhas: null })
      return
    }

    const planilha = lerCsv(await arquivo.text())
    const problema = validar(planilha, colunas)
    if (problema) {
      setErro(problema)
      return
    }
    aoCarregar({ nome: arquivo.name, arquivo, linhas: planilha.linhas })
  }

  return (
    <div>
      <label
        onDragOver={(evento) => {
          evento.preventDefault()
          setArrastando(true)
        }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(evento) => {
          evento.preventDefault()
          setArrastando(false)
          const [arquivo] = evento.dataTransfer.files
          if (arquivo) lerArquivo(arquivo)
        }}
        className={`flex cursor-pointer flex-wrap items-center gap-4 rounded-[2px] border-[1.5px] border-dashed p-5 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink ${
          arrastando ? 'border-ink bg-tinta-clara' : 'border-tinta-media hover:border-ink hover:bg-card-soft'
        }`}
      >
        <FileSpreadsheet aria-hidden="true" className="size-8 shrink-0 text-ink" />
        <span className="min-w-[200px] flex-1">
          <span className="block text-[15px] font-medium text-navy">Escolha o arquivo ou solte aqui</span>
          <span id={idDica} className="mt-0.5 block text-[14px]">
            CSV ou Excel com {colunas.length === 1 ? 'a coluna' : 'as colunas'} {colunas.join(', ')}, até {LIMITE_LINHAS} linhas
          </span>
        </span>
        <input
          type="file"
          accept=".csv,.xlsx,.xlsm"
          aria-describedby={idDica}
          className="sr-only"
          onChange={(evento) => {
            const [arquivo] = evento.target.files
            if (arquivo) lerArquivo(arquivo)
            evento.target.value = ''
          }}
        />
      </label>

      {erro && (
        <p role="alert" className="mt-2.5 text-[14.5px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </div>
  )
}

export default UploadLote
