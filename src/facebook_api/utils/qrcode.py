import io
import secrets
import time

import qrcode
from qrcode.image.pil import PilImage

from facebook_api.config import settings

_pending_tokens: dict[str, float] = {}


def create_qr_token() -> str:
    token = secrets.token_urlsafe(32)
    _pending_tokens[token] = time.time()
    return token


def validate_qr_token(token: str) -> bool:
    expiry = _pending_tokens.get(token)
    if expiry is None:
        return False
    if time.time() - expiry > settings.QR_TOKEN_TTL:
        _pending_tokens.pop(token, None)
        return False
    return True


def consume_qr_token(token: str) -> bool:
    if validate_qr_token(token):
        _pending_tokens.pop(token, None)
        return True
    return False


def generate_qr_image(url: str) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_qr_ascii(url: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    module_count = qr.modules_count
    matrix = qr.get_matrix()

    lines = []
    for row in range(0, module_count, 2):
        line_chars = []
        for col in range(module_count):
            top = matrix[row][col]
            bottom = matrix[row + 1][col] if row + 1 < module_count else False
            if top and bottom:
                line_chars.append("█")
            elif top and not bottom:
                line_chars.append("▀")
            elif not top and bottom:
                line_chars.append("▄")
            else:
                line_chars.append(" ")
        lines.append("".join(line_chars))
    return "\n".join(lines)
