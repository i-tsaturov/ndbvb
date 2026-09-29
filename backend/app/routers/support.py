"""Support tickets. The close action is an operator function that was put
on the customer-facing router — only the UI hides the button (BFLA)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..models import KycDocument, SupportTicket, User
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/support", tags=["support"])


class TicketBody(BaseModel):
    subject: str
    message: str


@router.get("/tickets", summary="My support tickets")
def my_tickets(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.created_at.desc())
        .all()
    )
    return [
        {"id": t.id, "subject": t.subject, "message": t.message, "status": t.status}
        for t in rows
    ]


@router.post("/tickets", summary="Create a support ticket")
def create_ticket(body: TicketBody, user: User = Depends(get_current_user), db=Depends(get_db)):
    ticket = SupportTicket(user_id=user.id, subject=body.subject, message=body.message)
    db.add(ticket)
    db.commit()
    return {"id": ticket.id, "status": ticket.status}


@router.post("/tickets/{ticket_id}/close", summary="Close a ticket (operator action)")
def close_ticket(ticket_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status == "closed":
        raise HTTPException(status_code=409, detail="Ticket is already closed")
    ticket.status = "closed"
    ticket.closed_by = user.id
    db.commit()
    return {"id": ticket.id, "status": ticket.status, "closed_by": user.id}


@router.delete("/kyc/{document_id}", summary="Delete a KYC document")
def delete_kyc(document_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    doc = db.get(KycDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    return {"status": "deleted", "id": document_id}
