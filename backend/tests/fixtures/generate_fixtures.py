"""
Generate sample fixture documents for the OCR service tests.

Run once from backend/:
    python tests/fixtures/generate_fixtures.py

Produces:
    tests/fixtures/sample_documents/native_text.pdf    – 1-page PDF with real text
    tests/fixtures/sample_documents/scanned_page.png   – PNG image of text (simulates a scan)
    tests/fixtures/sample_documents/scanned_pdf.pdf    – 1-page PDF whose content is an
                                                          embedded image (no native text)
    tests/fixtures/sample_documents/multi_page.pdf     – 2-page: page 1 native, page 2 image
"""

import io
import pathlib

HERE = pathlib.Path(__file__).parent
OUT = HERE / "sample_documents"
OUT.mkdir(exist_ok=True)


def _make_png_with_text(text: str, width: int = 400, height: int = 100) -> bytes:
    """Return PNG bytes containing *text* rendered in a simple bitmap font."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, 10), text, fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_native_pdf(text: str) -> bytes:
    """Return a 1-page PDF with *text* as real selectable text."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((72, 72), text, fontsize=14)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_image_pdf(png_bytes: bytes) -> bytes:
    """Return a 1-page PDF where the only content is an embedded image (no text layer)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(72, 72, 523, 200)
    page.insert_image(rect, stream=png_bytes)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_multi_page_pdf(text_page: str, image_png: bytes) -> bytes:
    """Return a 2-page PDF: page 1 has real text, page 2 has only an embedded image."""
    import fitz

    doc = fitz.open()

    # Page 1 — native text
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 72), text_page, fontsize=14)

    # Page 2 — image only
    p2 = doc.new_page(width=595, height=842)
    rect = fitz.Rect(72, 72, 523, 200)
    p2.insert_image(rect, stream=image_png)

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


if __name__ == "__main__":
    sample_text = "Invoice Total: $1,234.56\nDate: 2024-01-15\nVendor: Acme Corp"
    png_bytes = _make_png_with_text(sample_text, width=500, height=120)

    # 1. Native-text PDF
    native_pdf = _make_native_pdf(sample_text)
    (OUT / "native_text.pdf").write_bytes(native_pdf)
    print(f"  Created: {OUT / 'native_text.pdf'}  ({len(native_pdf)} bytes)")

    # 2. Scanned PNG
    (OUT / "scanned_page.png").write_bytes(png_bytes)
    print(f"  Created: {OUT / 'scanned_page.png'}  ({len(png_bytes)} bytes)")

    # 3. Image-only PDF (simulated scan)
    img_pdf = _make_image_pdf(png_bytes)
    (OUT / "scanned_pdf.pdf").write_bytes(img_pdf)
    print(f"  Created: {OUT / 'scanned_pdf.pdf'}  ({len(img_pdf)} bytes)")

    # 4. Multi-page PDF
    mp_pdf = _make_multi_page_pdf(sample_text, png_bytes)
    (OUT / "multi_page.pdf").write_bytes(mp_pdf)
    print(f"  Created: {OUT / 'multi_page.pdf'}  ({len(mp_pdf)} bytes)")

    print("\nAll fixtures generated successfully.")
