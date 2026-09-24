import io

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def qr_png(data, box_size=8, border=2):
    """Return a QR code for `data` as PNG bytes."""
    image = qrcode.make(data, error_correction=ERROR_CORRECT_M, box_size=box_size, border=border)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
