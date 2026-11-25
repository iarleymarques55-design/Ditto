import { useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import { NOME_DA_PASTA, NOME_DO_ARQUIVO } from '../download.js'
import { classeCodigo, classeTexto, classeTitulo } from './campos.js'

const PAGINA_DE_EXTENSOES = 'chrome://extensions'

// O painel não pode abrir páginas internas do Chrome: a pessoa copia o endereço e cola numa aba
function CopiarEndereco() {
  const [copiado, setCopiado] = useState(false)

  async function copiar() {
    try {
      await navigator.clipboard.writeText(PAGINA_DE_EXTENSOES)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2500)
    } catch {
      setCopiado(false)
    }
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <code className={classeCodigo}>{PAGINA_DE_EXTENSOES}</code>
      <Botao variante="contorno" onClick={copiar}>
        {copiado ? 'Endereço copiado' : 'Copiar endereço'}
      </Botao>
      <output className="sr-only">{copiado ? 'Endereço copiado' : ''}</output>
    </div>
  )
}

function Passo({ numero, titulo, children }) {
  return (
    <li className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-3 sm:grid-cols-[2.75rem_minmax(0,1fr)]">
      {/* Número escrito à mão na margem, como anotação num manual */}
      <span aria-hidden="true" className="font-hand text-[34px] leading-none font-bold text-ink sm:text-[40px]">
        {numero}
      </span>
      <div className="pt-1">
        <h3 className="font-display text-[18px] leading-snug font-bold text-navy">{titulo}</h3>
        <div className={`mt-1.5 ${classeTexto}`}>{children}</div>
      </div>
    </li>
  )
}

function PassosInstalacao() {
  return (
    <section aria-labelledby="instalar-titulo">
      <h2 id="instalar-titulo" className={classeTitulo}>
        Instalar no seu Chrome
      </h2>
      <p className={`mt-1 ${classeTexto}`}>
        A extensão é o que grava as tarefas e roda as repetições no seu navegador. Ela ainda não está na loja do Chrome,
        então a instalação é feita à mão, uma vez em cada computador.
      </p>

      <ol className="mt-7 space-y-7">
        <Passo numero="1" titulo="Baixe a extensão">
          Clique em <strong>Baixar extensão</strong>, no quadro <strong>Neste Chrome</strong>. O arquivo{' '}
          <code className={classeCodigo}>{NOME_DO_ARQUIVO}</code> vai para a sua pasta Downloads. Ele já vem configurado
          para este Ditto: não precisa mudar nada dentro dele.
        </Passo>

        <Passo numero="2" titulo="Extraia a pasta e guarde num lugar fixo">
          <p>
            No Windows, clique com o botão direito no arquivo e escolha <strong>Extrair tudo</strong>. No Mac, dê dois
            cliques nele. Vai aparecer a pasta <code className={classeCodigo}>{NOME_DA_PASTA}</code>.
          </p>
          <p className="mt-2">
            Mova essa pasta para um lugar onde ela vai ficar, como <strong>Documentos</strong>. O Chrome lê os arquivos
            dela enquanto a extensão estiver instalada: se a pasta for apagada ou mudar de lugar, a extensão para de
            funcionar.
          </p>
        </Passo>

        <Passo numero="3" titulo="Abra a página de extensões do Chrome">
          Por segurança, nenhum site pode abrir essa página por você. Copie o endereço abaixo, abra uma aba nova, cole na
          barra de endereço e aperte Enter.
          <CopiarEndereco />
          <p className="mt-2 text-[14px] text-grafite">
            No Edge, o endereço é <code className={classeCodigo}>edge://extensions</code>. No Brave,{' '}
            <code className={classeCodigo}>brave://extensions</code>.
          </p>
        </Passo>

        <Passo numero="4" titulo="Ligue o Modo do desenvolvedor">
          É a chave no canto superior direito da página de extensões. Ela só libera o botão do próximo passo, que permite
          instalar extensões de fora da loja do Chrome. O resto do navegador continua igual.
        </Passo>

        <Passo numero="5" titulo="Carregue a pasta do Ditto">
          Clique em <strong>Carregar sem compactação</strong>, no canto superior esquerdo, e escolha a pasta{' '}
          <code className={classeCodigo}>{NOME_DA_PASTA}</code> que você guardou no passo 2. Escolha a pasta em si, a que
          tem o arquivo <code className={classeCodigo}>manifest.json</code> dentro, e não o arquivo .zip. O cartão{' '}
          <strong>Ditto: gravador de tarefas</strong> aparece na lista.
        </Passo>

        <Passo numero="6" titulo="Fixe o ícone na barra do Chrome">
          Clique no ícone de quebra-cabeça, ao lado da barra de endereço, e no alfinete ao lado do Ditto. Assim o ícone
          fica sempre à vista, e você percebe quando uma gravação está acontecendo.
        </Passo>

        <Passo numero="7" titulo="Volte aqui e recarregue a página">
          O quadro <strong>Neste Chrome</strong> muda para <strong>Instalada</strong>. Já dá para gravar tarefas. Para as
          repetições rodarem neste Chrome, com as contas em que você já entrou, ligue o executor logo abaixo.
          <div className="mt-3">
            <Botao onClick={() => window.location.reload()}>Recarregar esta página</Botao>
          </div>
        </Passo>
      </ol>
    </section>
  )
}

export default PassosInstalacao
