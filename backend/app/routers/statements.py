"""Statement export and the legacy corporate statement import.

The import accepts two legacy formats used by the desktop accounting tools
of corporate clients: an XML format (parsed with full entity expansion,
because their files use shared entity catalogs) and a binary .bnk format
(pickled by the desktop tool).
"""
import pickle
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from lxml import etree

from ..db import get_db
from ..models import User
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/statements", tags=["statements"])

@router.get("/{account_id}/pdf", summary="Legacy statement stub -> redirect")
def statement_pdf_legacy(account_id: int, user: User = Depends(get_current_user)):
    return RedirectResponse(f"/api/v1/accounts/{account_id}/statement.pdf",
                            status_code=307)


@router.post("/import", summary="Import a corporate statement (XML/binary)")
async def import_statement(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    data = await file.read()
    filename = file.filename or ""

    if filename.lower().endswith((".bnk", ".dat", ".bin")):
        try:
            obj = pickle.loads(data)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unpickling failed: {exc}")
        return {
            "status": "processed",
            "format": "legacy-binary",
            "result": str(obj)[:400],
        }

    try:
        parser = etree.XMLParser(resolve_entities=True, no_network=False)
        tree = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"XML parsing failed: {exc}")

    fields = {}
    for tag in ("account", "period", "note"):
        node = tree.find(tag)
        fields[tag] = node.text if node is not None else ""
    return {
        "status": "processed",
        "format": "xml",
        "import_id": uuid.uuid4().hex,
        "fields": fields,
    }
