import io

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.exceptions import BusinessRuleError

AVATAR_SIZE = (256, 256)
MAX_AVATAR_BYTES = 3 * 1024 * 1024
_ACCEPTED_FORMATS = ("PNG", "JPEG", "WEBP")
# Um arquivo pequeno pode declarar uma imagem gigante e estourar a memória ao abrir
_MAX_PIXELS = 40_000_000


def process_avatar(content: bytes) -> bytes:
    """Decodifica e regrava a foto. O que fica salvo é sempre uma imagem nova, gerada aqui:
    conteúdo escondido no arquivo enviado e metadados, como a localização, não sobrevivem."""
    if len(content) > MAX_AVATAR_BYTES:
        raise BusinessRuleError("A foto passa de 3 MB. Escolha uma imagem menor.")

    try:
        with Image.open(io.BytesIO(content), formats=_ACCEPTED_FORMATS) as image:
            width, height = image.size
            if width * height > _MAX_PIXELS:
                raise BusinessRuleError("A foto é grande demais. Escolha uma imagem menor.")
            upright = ImageOps.exif_transpose(image).convert("RGB")
            square = ImageOps.fit(upright, AVATAR_SIZE)

        output = io.BytesIO()
        square.save(output, format="WEBP", quality=85)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as error:
        raise BusinessRuleError(
            "Este arquivo não é uma imagem válida. Use PNG, JPG ou WebP."
        ) from error

    return output.getvalue()
