import re

# Palavras de botões que não têm volta. Na dúvida, o Ditto para e pergunta.
_IRREVERSIBLE = re.compile(
    r"\b(pagar|pague|pagamento|pagamentos|enviar|envie|transmitir|confirmar|confirme|excluir|exclua|apagar|apague|"
    r"remover|remova|deletar|assinar|assine|finalizar|finalize|transferir|comprar|contratar|"
    r"cancelar|emitir|pay|send|submit|confirm|delete|remove|purchase|buy|sign)\b",
    re.IGNORECASE,
)


def looks_irreversible(text: str | None) -> bool:
    return bool(text and _IRREVERSIBLE.search(text))
