import { useEffect, useState } from 'react'
import Fita from '../../../components/landing/mesa/Fita.jsx'
import { consultarExtensao, extensaoInstalada } from '../../fluxos/extensao.js'
import { ENDERECO_DOWNLOAD, NOME_DO_ARQUIVO, situacaoDoDownload } from '../download.js'

const AVISO_DOWNLOAD = {
  indisponivel:
    'O download ainda não foi configurado neste servidor. Quem cuida do Ditto precisa preencher VITE_RELE_URL e PAINEL_URL no serviço do painel.',
  desenvolvimento:
    'No ambiente de desenvolvimento não há pacote para baixar: carregue a pasta extension do projeto no passo 5.',
}

// O post-it preso na folha: diz se a extensão está neste Chrome e entrega o arquivo para instalar.
function NesteChrome() {
  // A extensão marca a página assim que ela começa a carregar: dá para saber já no primeiro desenho
  const [instalada] = useState(extensaoInstalada)
  const [versao, setVersao] = useState(null)
  const [download, setDownload] = useState(null)

  useEffect(() => {
    let ativo = true
    if (instalada) consultarExtensao().then((resposta) => ativo && setVersao(resposta?.version ?? null))
    situacaoDoDownload().then((situacao) => ativo && setDownload(situacao))
    return () => {
      ativo = false
    }
  }, [instalada])

  return (
    <section aria-labelledby="neste-chrome-titulo" className="post-it relative px-6 pt-8 pb-6 lg:rotate-[0.8deg]">
      <Fita className="-top-2.5 left-1/2 -translate-x-1/2 rotate-1" />

      <h2 id="neste-chrome-titulo" className="font-display text-[22px] leading-tight font-bold text-navy">
        Neste Chrome
      </h2>

      <p className="mt-3 flex items-start gap-3 text-[15px] text-navy" aria-live="polite">
        <span
          aria-hidden="true"
          className={`mt-[7px] size-2.5 shrink-0 rounded-full ring-4 ring-papel-folha/70 ${
            instalada ? 'bg-ok-texto' : 'bg-grafite'
          }`}
        />
        <span>
          {instalada && (
            <>
              <strong>Instalada</strong>
              {versao && <span className="text-grafite">, versão {versao}</span>}
            </>
          )}
          {!instalada && (
            <>
              <strong>Não instalada.</strong> Siga os passos desta página. Leva uns dois minutos.
            </>
          )}
        </span>
      </p>

      {download === 'disponivel' && (
        <a
          href={ENDERECO_DOWNLOAD}
          download={NOME_DO_ARQUIVO}
          className="mt-5 inline-flex min-h-11 w-full items-center justify-center rounded-full bg-ink px-5 text-[14.5px] font-medium text-white shadow-botao hover:brightness-110"
        >
          {instalada ? 'Baixar de novo' : 'Baixar extensão'}
        </a>
      )}
      {AVISO_DOWNLOAD[download] && <p className="mt-4 text-[13.5px] leading-relaxed text-grafite">{AVISO_DOWNLOAD[download]}</p>}

      <p className="mt-4 border-t border-dashed border-tinta-media pt-3 text-[13.5px] leading-relaxed text-grafite">
        Funciona no Chrome, no Edge e no Brave, no computador. Celular não tem extensões.
      </p>
    </section>
  )
}

export default NesteChrome
