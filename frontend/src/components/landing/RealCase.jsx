import { Check } from 'lucide-react'

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

function TabelaExecucao() {
  return (
    <div className="rounded-xl border border-line bg-card p-4 shadow-card sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-[14.5px] font-medium text-navy">Execução de 05/10, às 07:10</h3>
        <p className="text-[12px] font-medium text-ok">25 de 25 concluídas</p>
      </div>

      <table className="mt-3 w-full text-left text-[13px]">
        <caption className="sr-only">Lojas processadas na execução de 05/10</caption>
        <thead>
          <tr className="text-[11.5px] text-muted">
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
              <tr key={loja.resumo}>
                <td colSpan={4} className="py-[7px] pl-6 text-muted">
                  {loja.resumo}
                </td>
              </tr>
            ) : (
              <tr key={loja.nome}>
                <td className="py-[7px]">
                  <span className="flex size-[17px] items-center justify-center rounded-full bg-ok text-white">
                    <Check size={11} strokeWidth={3} />
                    <span className="sr-only">Concluída</span>
                  </span>
                </td>
                <td className="py-[7px] text-navy">
                  {loja.nome}
                  {loja.reparo && (
                    <span className="ml-1.5 inline-block rounded-[3px] bg-ink px-1.5 py-px align-[1px] text-[10px] whitespace-nowrap text-white">
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

      <p className="mt-2 text-[13px]">
        Tudo salvo em <span className="font-medium text-ink">relatorios/09-2026</span>, sem ninguém clicar.
      </p>
    </div>
  )
}

function PortalMudou() {
  return (
    <div className="lg:pt-2.5 lg:pr-3">
      <h3 className="text-[15.5px] font-medium text-navy">Nesse mesmo dia, o portal mudou</h3>
      <p className="mt-1.5 text-[13px] leading-[1.6]">
        O botão de exportar saiu da tela e foi para dentro de um menu. Um robô comum teria parado nas 25 lojas.
      </p>

      <div aria-hidden="true" className="mt-5 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-2.5">
        <div className="rounded-lg border border-line bg-card p-3.5 shadow-card">
          <p className="text-[11.5px] text-muted">Em setembro</p>
          <span className="mt-3 block rounded-[3px] bg-navy py-1.5 text-center text-[11.5px] text-white">
            Exportar PDF
          </span>
          <p className="mt-3 text-[11px] text-muted">direto na tela</p>
        </div>

        <span className="self-center text-[15px] text-ink">›</span>

        <div className="rounded-lg border border-line bg-card p-3.5 shadow-card">
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
        </div>
      </div>

      <p className="mt-4 text-[13px] leading-[1.6]">
        O Ditto achou o novo caminho sozinho na loja 01 e usou nas outras 24.{' '}
        <strong className="font-medium text-ok">Nenhuma intervenção.</strong>
      </p>
    </div>
  )
}

function RealCase() {
  return (
    <section aria-labelledby="caso-real-titulo" className="bg-lavanda pt-14 pb-10 lg:pt-16">
      <div className="shell">
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_400px] lg:gap-10">
          <div className="lg:pt-5">
            <h2 id="caso-real-titulo" className="font-display text-[28px] leading-[1.15] font-bold text-navy sm:text-[34px]">
              Um caso real: 25 relatórios todo dia 5
            </h2>
            <p className="mt-5 max-w-[600px] text-[15.5px] leading-[1.75]">
              A Carla, do financeiro de uma rede com 25 lojas, entrava no portal do fornecedor e baixava o relatório
              de cada loja, um por um. Ela gravou a tarefa uma vez e passou a planilha com as lojas.
            </p>
          </div>

          <dl className="grid grid-cols-2 rounded-xl bg-card-soft">
            {comparacao.map((item, indice) => (
              <div key={item.rotulo} className={`px-5 py-5 ${indice > 0 ? 'border-l border-line' : ''}`}>
                <dt className="text-[11.5px] text-muted">{item.rotulo}</dt>
                <dd className={`mt-2 text-[24px] leading-tight font-medium ${item.cor}`}>{item.valor}</dd>
                <dd className="mt-2 text-[12px] leading-snug text-muted">{item.detalhe}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="mt-8 grid gap-6 rounded-xl bg-card-soft p-4 sm:p-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-7">
          <TabelaExecucao />
          <PortalMudou />
        </div>
      </div>
    </section>
  )
}

export default RealCase
