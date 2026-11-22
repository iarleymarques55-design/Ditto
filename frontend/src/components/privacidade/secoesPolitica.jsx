import { EMAIL_CONTATO } from '../landing/navLinks.js'

// Texto da Política de privacidade. Cada seção vira um item do sumário e um <section> da página.
// Ao mudar o que o sistema coleta ou com quem fala, atualize aqui e a data em ATUALIZADA_EM.

export const ATUALIZADA_EM = '21 de novembro de 2026'

export function Email() {
  return (
    <a
      href={`mailto:${EMAIL_CONTATO}`}
      className="font-medium [overflow-wrap:anywhere] text-ink underline decoration-ink/40 underline-offset-4 hover:decoration-ink"
    >
      {EMAIL_CONTATO}
    </a>
  )
}

// Uma linha de ficha: o nome à esquerda, o que é à direita
function Item({ titulo, children }) {
  return (
    <div className="grid gap-x-6 gap-y-1 border-t border-line py-4 first:border-t-0 sm:grid-cols-[170px_minmax(0,1fr)]">
      <dt className="font-semibold text-navy">{titulo}</dt>
      <dd>{children}</dd>
    </div>
  )
}

// Tabela com cara de livro de registro: cabeçalho em letra pequena e linhas finas
function Tabela({ legenda, colunas, linhas }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full border-collapse text-left text-[15px] leading-snug">
        <caption className="sr-only">{legenda}</caption>
        <thead>
          <tr className="border-b-2 border-navy/80">
            {colunas.map((coluna) => (
              <th key={coluna} scope="col" className="py-2 pr-4 text-[13.5px] font-semibold text-navy">
                {coluna}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map(([primeira, ...resto]) => (
            <tr key={primeira} className="border-b border-line align-top">
              <th scope="row" className="py-3 pr-4 font-semibold text-navy sm:whitespace-nowrap">
                {primeira}
              </th>
              {resto.map((celula, indice) => (
                // As colunas são fixas: a posição identifica cada célula
                // oxlint-disable-next-line react/no-array-index-key
                <td key={indice} className="py-3 pr-4">
                  {celula}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export const secoes = [
  {
    id: 'quem-somos',
    titulo: 'Quem cuida dos seus dados',
    conteudo: (
      <>
        <p>
          O Ditto é um projeto de código aberto mantido por Iarley Marques, que é o controlador dos dados tratados aqui,
          nos termos da Lei Geral de Proteção de Dados (Lei 13.709/2018, a LGPD). Para qualquer assunto sobre os seus
          dados, escreva para <Email />.
        </p>
        <p>
          Os dados que você coloca nas suas tarefas e planilhas, como nomes, CNPJs ou dados de clientes e funcionários,
          são seus. Para eles, o Ditto age em seu nome: só usa esses dados para rodar as tarefas que você pediu. Você é
          quem decide o que entra e precisa ter o direito de usar esses dados.
        </p>
      </>
    ),
  },
  {
    id: 'o-que-coletamos',
    titulo: 'O que o Ditto guarda',
    conteudo: (
      <dl>
        <Item titulo="Sua conta">
          Nome, e-mail, a foto ou avatar que você escolher e a sua senha, guardada só como hash (bcrypt), que não pode
          ser revertido. Se você entra com o Google, recebemos do Google apenas o seu nome, e-mail e um identificador
          da conta, sem acesso a mais nada dela.
        </Item>
        <Item titulo="Tarefas gravadas">
          Os passos que você fez durante a gravação: o endereço dos sites, os cliques, o texto digitado em campos comuns
          e uma descrição de cada elemento da tela (texto, rótulo, posição) para reconhecê-lo depois. O valor de campos
          de senha, cartão e código nunca é lido nem enviado.
        </Item>
        <Item titulo="Acessos salvos">
          Usuário e senha dos sites que você cadastra para o Ditto entrar por você. Eles ficam criptografados no banco
          (Fernet) e só são abertos no momento de digitar no site certo.
        </Item>
        <Item titulo="Planilhas e execuções">
          As linhas que você envia para repetir uma tarefa, os dados lidos das telas durante a execução, o histórico de
          cada execução e os registros de reparo e de pedidos de ajuda.
        </Item>
        <Item titulo="Arquivos baixados">
          Relatórios, PDFs e outros arquivos que as tarefas baixam ficam guardados por 30 dias, para você baixar no
          painel. Depois disso, são apagados sozinhos.
        </Item>
        <Item titulo="Criar com IA">
          O pedido que você escreve, o endereço inicial, os passos montados e as respostas que você dá às perguntas da
          IA.
        </Item>
      </dl>
    ),
  },
  {
    id: 'extensao',
    titulo: 'O que a extensão do Chrome vê',
    conteudo: (
      <>
        <p>
          A extensão pede acesso a todos os sites porque uma tarefa pode acontecer em qualquer portal. Mesmo assim, ela
          só grava e controla as abas abertas pelo painel do Ditto e as janelas abertas por elas. Nas outras abas,
          nenhum script é colocado e nada é lido.
        </p>
        <p>
          Com o executor ligado, as tarefas rodam no seu Chrome, com as contas que já estão logadas nele. Os arquivos
          baixados passam pela sua pasta Downloads. Para entregá-los ao Ditto, a extensão busca o mesmo endereço de
          novo, com as suas contas, e manda o conteúdo pela conexão cifrada; depois, apaga o arquivo da pasta. A
          extensão usa tokens próprios, que não dão acesso à sua conta no painel.
        </p>
      </>
    ),
  },
  {
    id: 'ia',
    titulo: 'O que vai para a inteligência artificial',
    conteudo: (
      <>
        <p>
          A IA só entra quando um site mudou e o Ditto não acha mais um elemento, ou quando você usa o Criar com IA.
          Nesses momentos, ela recebe a intenção do passo e um resumo da tela: os elementos visíveis e seus rótulos, um
          trecho do texto da página (até cerca de 1.500 caracteres) e a primeira linha das tabelas. O que está digitado
          dentro dos campos não vai.
        </p>
        <p>
          Antes de sair do Ditto, esse conteúdo passa por um filtro que remove senhas, acessos salvos e outros valores
          sensíveis. Se algum segredo ainda aparecer, a chamada é cancelada. Hoje o provedor de IA é a Groq, que
          processa o pedido e devolve a resposta.
        </p>
      </>
    ),
  },
  {
    id: 'para-que-usamos',
    titulo: 'Para que usamos os dados',
    conteudo: (
      <>
        <ul className="list-disc space-y-2 pl-5 marker:text-tinta-media">
          <li>Criar e manter a sua conta e deixar você entrar nela.</li>
          <li>Gravar, guardar, rodar e reparar as suas tarefas, inclusive nos horários agendados.</li>
          <li>
            Avisar por e-mail quando uma execução falha ou precisa da sua ajuda. Você pode desligar esses avisos na
            página da conta; os pedidos continuam no painel.
          </li>
          <li>Proteger o serviço contra abuso, como limitar tentativas de login e o tamanho dos envios.</li>
        </ul>
        <p>
          A base legal é a execução do serviço que você pediu ao criar a conta (art. 7º, V, da LGPD) e o legítimo
          interesse em manter o serviço seguro (art. 7º, IX). Não vendemos dados, não mostramos anúncios e não usamos
          ferramentas de rastreamento ou de análise de público.
        </p>
      </>
    ),
  },
  {
    id: 'com-quem-compartilhamos',
    titulo: 'Com quem os dados são compartilhados',
    conteudo: (
      <>
        <p>Só com os serviços que fazem o Ditto funcionar, e só com o necessário para cada um:</p>
        <Tabela
          legenda="Serviços que recebem dados do Ditto"
          colunas={['Serviço', 'O que recebe', 'Quando']}
          linhas={[
            ['Railway', 'Tudo o que o Ditto guarda: hospeda o painel, a API, o banco e os arquivos', 'Sempre'],
            ['Groq', 'O resumo filtrado da tela descrito acima', 'Quando a IA é chamada'],
            ['Brevo', 'O seu e-mail e o texto do aviso', 'Quando uma execução falha ou pede a sua ajuda'],
            [
              'Google',
              'O pedido de login e o seu endereço IP, pelas fontes usadas nas páginas',
              'Se você entra com o Google, e ao abrir as páginas',
            ],
          ]}
        />
        <p>
          Alguns desses serviços guardam ou processam dados fora do Brasil. Essa transferência acontece só para
          prestar o serviço e segue o que a LGPD pede (art. 33). Também podemos informar dados a autoridades quando a
          lei obrigar.
        </p>
      </>
    ),
  },
  {
    id: 'navegador',
    titulo: 'O que fica no seu navegador',
    conteudo: (
      <p>
        O painel guarda no armazenamento local do navegador (localStorage) o token que mantém você conectado. Ele vale
        por 8 horas e é apagado quando você sai da conta. O Ditto não usa cookies de rastreamento nem de publicidade.
      </p>
    ),
  },
  {
    id: 'por-quanto-tempo',
    titulo: 'Por quanto tempo guardamos',
    conteudo: (
      <>
        <Tabela
          legenda="Por quanto tempo cada dado fica guardado"
          colunas={['O quê', 'Fica guardado']}
          linhas={[
            ['Arquivos baixados', '30 dias. Depois, são apagados sozinhos'],
            [
              'Conta, tarefas, acessos, execuções e agendas',
              'Enquanto a conta existir, ou até você apagar cada item no painel',
            ],
            ['Tudo, ao excluir a conta', 'Nada. É apagado na hora, junto com os arquivos'],
          ]}
        />
      </>
    ),
  },
  {
    id: 'seguranca',
    titulo: 'Como protegemos',
    conteudo: (
      <p>
        Senhas da conta ficam só como hash, e os acessos aos sites ficam criptografados. A conexão com o painel é
        cifrada (HTTPS), cada pessoa só vê as próprias tarefas e o login expira sozinho. Ações que não têm volta, como
        pagar ou enviar, pedem a sua confirmação, e o Ditto para e chama você diante de um CAPTCHA, sem tentar
        contorná-lo. Nenhum sistema é infalível: se acontecer um incidente que possa afetar você, avisaremos você e a
        Autoridade Nacional de Proteção de Dados (ANPD).
      </p>
    ),
  },
  {
    id: 'seus-direitos',
    titulo: 'Seus direitos',
    conteudo: (
      <>
        <p>Pela LGPD (art. 18), você pode, a qualquer momento:</p>
        <Tabela
          legenda="Seus direitos e onde exercer cada um"
          colunas={['Você pode', 'Onde']}
          linhas={[
            ['Corrigir os seus dados', 'Na página da conta, no painel: nome, foto e senha'],
            ['Desligar os avisos por e-mail', 'Na página da conta, no painel'],
            ['Excluir a conta e tudo ligado a ela', 'Na página da conta, no painel. Vale na hora'],
            ['Receber uma cópia dos seus dados', <Email key="copia" />],
            ['Saber com quem eles foram compartilhados', <Email key="compartilhados" />],
            ['Pedir que dados desnecessários sejam apagados', <Email key="apagar" />],
          ]}
        />
        <p>
          Pedidos por e-mail são respondidos em até 15 dias. Se não ficar satisfeito, você também pode procurar a
          Autoridade Nacional de Proteção de Dados (ANPD).
        </p>
      </>
    ),
  },
  {
    id: 'menores',
    titulo: 'Menores de idade',
    conteudo: (
      <p>O Ditto é feito para uso profissional e não se destina a menores de 18 anos.</p>
    ),
  },
  {
    id: 'mudancas',
    titulo: 'Mudanças nesta política',
    conteudo: (
      <p>
        Se esta política mudar, a data no topo da página muda junto. Quando a mudança for importante, como um novo
        serviço que recebe os seus dados, você será avisado por e-mail ou no painel antes de ela valer.
      </p>
    ),
  },
]
