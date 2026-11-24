import re

# Palavras de botões que não têm volta. Na dúvida, o Ditto para e pergunta. Vale para a gravação
# (o passo fica marcado como "sem volta"), para a repetição e para o Criar com IA. "Aceitar",
# "Concordo" e "Pix" ficam de fora de propósito: aparecem em avisos de cookies e em menus, e
# fariam toda tarefa agendada parar pedindo confirmação.
_IRREVERSIBLE = re.compile(
    r"\b("
    # pagar e mexer em dinheiro
    r"pagar|pague|pagamentos?|transferir|transfira|transfer[eê]ncias?|comprar|compre|"
    r"contratar|contrate|quitar|liquidar|efetivar|efetive|"
    # enviar e confirmar
    r"enviar|envie|transmitir|transmita|confirmar|confirme|finalizar|finalize|concluir|conclua|"
    r"emitir|emita|protocolar|publicar|publique|"
    # aprovar e autorizar
    r"aprovar|aprove|autorizar|autorize|assinar|assine|"
    # apagar e encerrar
    r"excluir|exclua|apagar|apague|remover|remova|deletar|cancelar|cancele|desativar|"
    r"encerrar|encerre|revogar|revogue|"
    # inglês
    r"pay|send|submit|confirm|delete|remove|purchase|buy|sign|approve|authori[sz]e|"
    r"transfer|publish|checkout|place order"
    r")\b",
    re.IGNORECASE,
)


def looks_irreversible(text: str | None) -> bool:
    return bool(text and _IRREVERSIBLE.search(text))
