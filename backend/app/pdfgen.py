"""Dependency-free PDF generation (uncompressed text objects).

Objects are plain text (no stream compression) so the documents are readable
in the raw bytes — statements and receipts both use this.
"""
PAGE_W, PAGE_H = 595, 842
MARGIN_X, TOP_Y, LINE = 50, 790, 15
LINES_PER_PAGE = 46


def _esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(lines: list[str]) -> str:
    parts = [f"BT /F1 10 Tf {MARGIN_X} {TOP_Y} Td {LINE} TL"]
    for line in lines[:LINES_PER_PAGE]:
        parts.append(f"({_esc(line)}) Tj T*")
    parts.append("ET")
    return " ".join(parts)


def build_pdf(pages: list[list[str]]) -> bytes:
    """Build a one-font, multi-page PDF document from plain text lines."""
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []

    def add(body: str) -> int:
        offsets.append(len(out))
        out.extend(body.encode("latin-1", "replace"))
        out.extend(b"\n")
        return len(offsets)

    add("1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    add(f"2 0 obj<</Type/Pages/Kids[{kids}]/Count {len(pages)}>>endobj")
    add("3 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>endobj")
    for i, lines in enumerate(pages):
        stream = _page_stream(lines)
        add(f"{4 + 2 * i} 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 {PAGE_W} {PAGE_H}]"
            f"/Resources<</Font<</F1 3 0 R>>>>/Contents {5 + 2 * i} 0 R>>endobj")
        add(f"{5 + 2 * i} 0 obj<</Length {len(stream)}>>stream\n{stream}\nendstream endobj")

    xref_at = len(out)
    count = len(offsets) + 1
    out.extend(f"xref\n0 {count}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer<</Size {count}/Root 1 0 R>>\nstartxref\n{xref_at}\n%%EOF".encode())
    return bytes(out)


def paginate(lines: list[str]) -> list[list[str]]:
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]
    if not pages:
        pages = [["(no data)"]]
    for idx, page in enumerate(pages, start=1):
        page.append("")
        page.append(f"OnlineBank - page {idx} of {len(pages)}")
    return pages
