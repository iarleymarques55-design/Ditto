from pydantic import BaseModel, Field


class Page[T](BaseModel):
    """Uma página de uma listagem."""

    items: list[T] = Field(description="Registros desta página.")
    total: int = Field(description="Total de registros, somando todas as páginas.")
    limit: int = Field(description="Tamanho máximo da página pedido.")
    offset: int = Field(description="Quantos registros foram pulados.")
