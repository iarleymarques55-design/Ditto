import Botao from '../../../components/ui/Botao.jsx'

// Aparece quando algo espera na fila e nenhum Chrome está ligado a esta conta pela extensão.
// Sem ele, o pedido ficava "Na fila" para sempre, inclusive quando a extensão estava ligada à
// conta de outra pessoa (ou à sua outra conta, de e-mail e senha ou do Google).
function AvisoSemChrome({ oQue = 'Isto' }) {
  return (
    <div aria-live="polite" className="rounded-[10px] bg-rec/10 px-4 py-3.5 text-[14.5px] leading-relaxed text-navy">
      <p className="font-medium">{oQue} só começa quando um Chrome estiver ligado a esta conta.</p>
      <p className="mt-1">
        Nenhum Chrome está ligado agora. Se a extensão estiver ligada a outra conta, ela atende só a fila daquela conta. Abra a
        página da extensão e clique em Ligar neste Chrome.
      </p>
      <div className="mt-3">
        <Botao para="/painel/extensao">Abrir a página da extensão</Botao>
      </div>
    </div>
  )
}

export default AvisoSemChrome
