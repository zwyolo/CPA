"""CAPTCHA solving using ddddocr."""

import base64


def solve(image_b64: str) -> str:
    import ddddocr

    img_bytes = base64.b64decode(image_b64)
    ocr = ddddocr.DdddOcr(show_ad=False)
    ocr.set_ranges(6)
    result = ocr.classification(img_bytes).strip().upper()
    print(f"[CAPTCHA] ddddocr: {result}")
    return result
