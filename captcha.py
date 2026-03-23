"""
CAPTCHA solving helpers.
Supports: ddddocr (offline), 2captcha API, pytesseract OCR.
"""

import base64
import urllib.request
import urllib.parse
from io import BytesIO
from typing import Optional

def solve(image_b64: str, method: str = "ddddocr", api_key: str = "") -> str:
    """
    Given a base64-encoded CAPTCHA image, return the solved text.
    """
    if method == "ddddocr":
        result = _solve_ddddocr(image_b64)
        if result:
            return result
        print("[CAPTCHA] ddddocr failed.")

    elif method == "2captcha":
        result = _solve_2captcha(image_b64, api_key)
        if result:
            return result
        print("[CAPTCHA] 2captcha failed.")

    elif method == "ocr":
        result = _solve_ocr(image_b64)
        if result:
            return result
        print("[CAPTCHA] OCR failed.")

    return ""

def _solve_ddddocr(image_b64: str) -> Optional[str]:
    try:
        import ddddocr
        img_bytes = base64.b64decode(image_b64)
        ocr = ddddocr.DdddOcr(show_ad=False)
        ocr.set_ranges("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz")
        result = ocr.classification(img_bytes)
        return result.strip().upper() if result else None
    except Exception as e:
        print(f"[CAPTCHA] ddddocr error: {e}")
        return None

def _solve_2captcha(image_b64: str, api_key: str) -> Optional[str]:
    if not api_key:
        print("[CAPTCHA] No 2captcha API key provided.")
        return None
    try:
        import json
        submit_url = "http://2captcha.com/in.php"
        data = urllib.parse.urlencode({
            "key": api_key,
            "method": "base64",
            "body": image_b64,
            "json": 1,
        }).encode()
        req = urllib.request.Request(submit_url, data=data)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        if result.get("status") != 1:
            return None

        captcha_id = result["request"]
        import time
        for _ in range(24):
            time.sleep(5)
            poll_url = f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1"
            with urllib.request.urlopen(poll_url, timeout=15) as resp:
                poll = json.loads(resp.read())
            if poll.get("status") == 1:
                return poll["request"]
        return None
    except Exception as e:
        print(f"[CAPTCHA] 2captcha exception: {e}")
        return None

def _solve_ocr(image_b64: str) -> Optional[str]:
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageOps
        img_data = base64.b64decode(image_b64)
        img = Image.open(BytesIO(img_data)).convert("L")
        img = ImageOps.autocontrast(img)
        img = img.filter(ImageFilter.SHARPEN)
        img = img.point(lambda x: 0 if x < 140 else 255)
        text = pytesseract.image_to_string(img, config="--psm 8 --oem 3").strip()
        return "".join(c for c in text if c.isalnum()).upper()
    except Exception:
        return None
