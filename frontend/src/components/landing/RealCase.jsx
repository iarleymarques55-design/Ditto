import { Check } from 'lucide-react'
import pilhaRelatorios from '../../assets/fotos/pilha-relatorios.webp'
import Anotacao from './mesa/Anotacao.jsx'

const comparacao = [
  { rotulo: 'Antes, todo mês', valor: '~2 horas', detalhe: 'feito à mão, loja por loja', cor: 'text-navy' },
  { rotulo: 'Agora, com o Ditto', valor: '4 min 38 s', detalhe: 'roda às 07:10, antes de ela chegar', cor: 'text-ink' },
]

const lojas = [
  { nome: 'Loja 01 - Shopping Norte', arquivo: 'loja-01_09-2026.pdf', tempo: '19 s', reparo: true },
  { nome: 'Loja 02 - Aldeota', arquivo: 'loja-02_09-2026.pdf', tempo: '10 s' },
  { nome: 'Loja 03 - Messejana', arquivo: 'loja-03_09-2026.pdf', tempo: '12 s' },
  { resumo: 'mais 21 lojas, todas concluídas' },
  { nome: 'Loja 25 - Eusébio', arquivo: 'loja-25_09-2026.pdf', tempo: '10 s' },
]

// Etiqueta de papel com furo, presa ao que ela identifica. O furo mostra o mata-borrão por baixo.
function Etiqueta({ rotulo, valor, detalhe, cor, className = '' }) {
  return (
    <dl className={`folha relative z-10 w-fit py-3 pr-6 pl-10 ${className}`}>
      <span aria-hidden="true" className="absolute top-1/2 left-3.5 size-3 -translate-y-1/2 rounded-full bg-lavanda shadow-[inset_1px_1px_2px_rgba(70,48,20,0.3)]" />
      <dt className="text-[11.5px] text-muted">{rotulo}</dt>
      <dd className={`mt-1 font-display text-[30px] leading-none font-bold ${cor}`}>{valor}</dd>
      <dd className="mt-1.5 text-[12px] leading-snug text-muted">{detalhe}</dd>
    </dl>
  )
}

// Prendedor de papel (binder clip) visto de cima.
function Prendedor({ className = '' }) {
  return (
    <span aria-hidden="true" className={`absolute z-10 h-5 w-14 rounded-[3px] bg-[#23202b] shadow-[1px_2px_3px_rgba(0,0,0,0.3)] ${className}`}>
      <span className="absolute -top-3 left-2 h-4 w-10 rounded-t-md border-2 border-b-0 border-[#9a98a3]" />
    </span>
  )
}

function TabelaExecucao() {
  return (
    <div className="folha relative px-4 pt-8 pb-5 sm:px-6">
      <Prendedor className="-top-2.5 left-10" />
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-[14.5px] font-medium text-navy">Execução de 05/10, às 07:10</h3>
        <p className="text-[12px] font-medium text-ok">25 de 25 concluídas</p>
      </div>

      <table className="mt-3 w-full text-left text-[13px]">
        <caption className="sr-only">Lojas processadas na execução de 05/10</caption>
        <thead>
          <tr className="border-b border-line text-[11.5px] text-muted">
            <th scope="col" className="w-6 pb-1 font-normal">
              <span className="sr-only">Situação</span>
            </th>
            <th scope="col" className="pb-1 font-normal">
              Loja
            </th>
            <th scope="col" className="hidden pb-1 font-normal md:table-cell">
              Arquivo salvo
            </th>
            <th scope="col" className="pb-1 text-right font-normal">
              Tempo
            </th>
          </tr>
        </thead>
        <tbody>
          {lojas.map((loja) =>
            loja.resumo ? (
              <tr key={loja.resumo} className="border-b border-dashed border-line">
                <td colSpan={4} className="py-[7px] pl-6 text-muted">
                  {loja.resumo}
                </td>
              </tr>
            ) : (
              <tr key={loja.nome} className="border-b border-dashed border-line last:border-b-0">
                <td className="py-[7px]">
                  <span className="flex size-[17px] items-center justify-center rounded-full bg-ok text-white">
                    <Check size={11} strokeWidth={3} />
                    <span className="sr-only">Concluída</span>
                  </span>
                </td>
                <td className="py-[7px] text-navy">
                  {loja.nome}
                  {loja.reparo && (
                    <span className="ml-1.5 inline-block rounded-[2px] border-[1.5px] border-ink bg-card px-1.5 py-px align-[1px] text-[10px] font-medium whitespace-nowrap text-ink">
                      reparo
                    </span>
                  )}
                </td>
                <td className="hidden py-[7px] md:table-cell">{loja.arquivo}</td>
                <td className="py-[7px] text-right text-navy">{loja.tempo}</td>
              </tr>
            ),
          )}
        </tbody>
      </table>

      <p className="mt-3 text-[13px]">
        Tudo salvo em <span className="font-medium text-ink">relatorios/09-2026</span>, sem ninguém clicar.
      </p>
    </div>
  )
}

// Ficha de fichário: linha vermelha no topo, como as de papelaria.
function Ficha({ className = '', children }) {
  return <div className={`folha border-t-2 border-t-rec/45 p-3.5 ${className}`}>{children}</div>
}

function PortalMudou() {
  return (
    <div className="grid items-center gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] md:gap-12">
      <div>
        <h3 className="font-display text-[20px] leading-snug font-bold text-navy">Nesse mesmo dia, o portal mudou</h3>
        <p className="mt-2 max-w-[440px] text-[14px] leading-[1.65]">
          O botão de exportar saiu da tela e foi para dentro de um menu. Um robô comum teria parado nas 25 lojas.
        </p>
        <p className="mt-3 max-w-[440px] text-[14px] leading-[1.65]">
          O Ditto achou o novo caminho sozinho na loja 01 e usou nas outras 24.{' '}
          <strong className="font-medium text-ok">Nenhuma intervenção.</strong>
        </p>
      </div>

      <div aria-hidden="true" className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3">
        <Ficha className="-rotate-2">
          <p className="text-[11.5px] text-muted">Em setembro</p>
          <span className="mt-3 block rounded-[3px] bg-navy py-1.5 text-center text-[11.5px] text-white">Exportar PDF</span>
          <p className="mt-3 text-[11px] text-muted">direto na tela</p>
        </Ficha>

        <span className="font-hand text-[26px] font-bold text-ink">›</span>

        <Ficha className="rotate-[1.5deg]">
          <p className="text-[11.5px] text-muted">Em outubro</p>
          <span className="mt-2 inline-block rounded-[3px] border border-line px-2 py-0.5 text-[11px] text-navy">
            Ações ▾
          </span>
          <div className="mt-1.5 rounded-[3px] border border-line p-1">
            <span className="block px-1.5 py-1 text-[10.5px] text-muted">Imprimir</span>
            <span className="block rounded-[2px] border border-dashed border-ink bg-lavanda px-1.5 py-1 text-[10.5px] text-ink">
              Baixar como PDF
            </span>
          </div>
        </Ficha>
      </div>
    </div>
  )
}

function RealCase() {
  const [antes, agora] = comparacao
  return (
    <section id="exemplo" aria-labelledby="caso-real-titulo" className="pb-20 lg:pb-28">
      <div className="shell">
        {/* Mata-borrão lavanda sobre a mesa: tudo do caso fica em cima dele */}
        <div className="rounded-[20px] bg-lavanda px-5 pt-10 pb-12 shadow-papel sm:px-8 lg:px-12 lg:pt-14 lg:pb-14">
          <h2 id="caso-real-titulo" className="font-display text-[28px] leading-[1.15] font-bold text-navy sm:text-[34px]">
            Um caso real: 25 relatórios todo dia 5
          </h2>
          <p className="mt-4 max-w-[600px] text-[15.5px] leading-[1.75]">
            A Carla, do financeiro de uma rede com 25 lojas, entrava no portal do fornecedor e baixava o relatório de cada
            loja, um por um. Ela gravou a tarefa uma vez e passou a planilha com as lojas.
          </p>

          <div className="mt-12 grid items-start gap-12 lg:grid-cols-[minmax(0,5fr)_auto_minmax(0,7fr)] lg:gap-6">
            <figure className="mx-auto w-full max-w-[340px] lg:mx-0">
              <Etiqueta {...antes} className="-mb-4 ml-4 rotate-[2deg]" />
              <div className="folha -rotate-[2.5deg] p-2.5 pb-3">
                <img
                  src={pilhaRelatorios}
                  alt="Pilha de relatórios impressos, baixados um por um"
                  width={900}
                  height={1125}
                  loading="lazy"
                  className="block aspect-[4/5] w-full object-cover"
                />
              </div>
            </figure>

            <Anotacao seta="direita" className="hidden self-center pt-24 text-center lg:block" classeSeta="mx-auto mt-1 h-8 w-20">
              gravou uma vez
            </Anotacao>

            <div>
              <Etiqueta {...agora} className="mb-6 ml-auto mr-6 -rotate-2 lg:-mb-3" />
              <TabelaExecucao />
            </div>
          </div>

          <div className="mt-14 border-t border-dashed border-tinta-media pt-10">
            <PortalMudou />
          </div>
        </div>
      </div>
    </section>
  )
}

export default RealCase
