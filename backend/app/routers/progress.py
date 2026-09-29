"""Personal progress panel: submit flags as you find them.

A solo training companion rather than a competition board: your nickname
scopes the solved state, hints are served alongside the challenge list (the
UI keeps them behind a toggle), and every submission is stored in the
database, so progress survives restarts (a debug /reset wipes it together
with the demo data).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..models import Challenge, Solve
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/progress", tags=["progress"])


@router.get("/challenges", summary="Task list (+my solved state)")
def challenges(nickname: str = "", db=Depends(get_db)):
    """Challenge list; with ?nickname= each row carries your solved state."""
    rows = db.query(Challenge).order_by(Challenge.id).all()
    solved_codes: set[str] = set()
    if nickname.strip():
        solved_codes = set(
            c.code
            for c in db.query(Challenge)
            .join(Solve, Solve.challenge_id == Challenge.id)
            .filter(Solve.nickname == nickname.strip())
            .all()
        )
    return [
        {
            "code": c.code,
            "title": c.title,
            "category": c.category,
            "points": c.points,
            "hint": c.hint,
            "solved": c.code in solved_codes,
        }
        for c in rows
    ]


class SubmitBody(BaseModel):
    nickname: str
    flag: str


@router.post("/submit", summary="Submit a flag")
def submit(body: SubmitBody, db=Depends(get_db)):
    if not body.nickname.strip() or not body.flag.strip():
        raise HTTPException(status_code=422, detail="Nickname and flag are required")
    challenge = db.query(Challenge).filter(Challenge.flag == body.flag.strip()).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Unknown flag")
    existing = (
        db.query(Solve)
        .filter(Solve.nickname == body.nickname.strip(), Solve.challenge_id == challenge.id)
        .first()
    )
    if existing:
        return {"status": "already solved", "challenge": challenge.title}
    db.add(Solve(nickname=body.nickname.strip(), challenge_id=challenge.id))
    db.commit()
    return {
        "status": "solved",
        "challenge": challenge.title,
        "points": challenge.points,
    }


@router.get("/state", summary="My progress counters")
def state(nickname: str, db=Depends(get_db)):
    """Your counters: solved codes, points, how many are left."""
    nickname = nickname.strip()
    rows = db.query(Challenge).order_by(Challenge.id).all()
    solved = (
        db.query(Challenge, Solve)
        .join(Solve, Solve.challenge_id == Challenge.id)
        .filter(Solve.nickname == nickname)
        .all()
        if nickname
        else []
    )
    solved_codes = [c.code for c, _ in solved]
    points = sum(c.points for c, _ in solved)
    return {
        "nickname": nickname,
        "solved": solved_codes,
        "solved_count": len(solved_codes),
        "remaining": len(rows) - len(solved_codes),
        "total": len(rows),
        "points": points,
        "points_total": sum(c.points for c in rows),
    }
