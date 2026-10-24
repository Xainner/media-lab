"""Private characters: a @handle with reference images and an optional LoRA from the owner's library.

Jobs never read this table: the composer and agents expand @handle into the job's own references and
loras, which pass the usual ownership checks at admission.
"""
from __future__ import annotations

import json
import secrets
import time

from pydantic import Field, field_validator

from .contracts import ArtifactRef
from .security import owner
from .tenancy import NotOwned
from .web_auth import Strict

IMAGE_KINDS = {"images", "references"}
CHARACTER_LIMIT = 50


class CharacterBody(Strict):
    handle: str = Field(pattern=r"^[A-Za-z0-9_]{2,24}$", description="Name used after @ in prompts.")
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=600, description="Short look description (English helps the models).")
    references: list[ArtifactRef] = Field(min_length=1, max_length=4, description="1–4 owned images; the first is the main one.")
    lora_id: str | None = Field(default=None, pattern=r"^lora_[0-9a-f]{16}$")

    @field_validator("handle")
    @classmethod
    def lower(cls, value: str) -> str:
        return value.lower()


class Characters:
    def __init__(self, store):
        self.store = store

    def _item(self, row, db) -> dict:
        refs = json.loads(row["references_json"])
        # A reference deleted from the library drops out instead of failing every later job.
        live = [r for r in refs if db.execute("SELECT 1 FROM artifacts WHERE uri=? AND owner_id=? AND sha256=?",
                                              (r["uri"], row["owner_id"], r["sha256"])).fetchone()]
        lora = db.execute("SELECT id,name,base,trigger,strength,status FROM loras WHERE id=? AND owner_id=?",
                          (row["lora_id"], row["owner_id"])).fetchone() if row["lora_id"] else None
        return {"id": row["id"], "handle": row["handle"], "name": row["name"], "description": row["description"],
                "references": live, "lora": dict(lora) if lora else None,
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def items(self) -> list[dict]:
        with self.store._db() as db:
            rows = db.execute("SELECT * FROM characters WHERE owner_id=? ORDER BY handle", (owner(),)).fetchall()
            return [self._item(r, db) for r in rows]

    def get(self, cid: str) -> dict:
        with self.store._db() as db:
            row = db.execute("SELECT * FROM characters WHERE id=? AND owner_id=?", (cid, owner())).fetchone()
            if not row:
                raise NotOwned("resource not found")
            return self._item(row, db)

    def save(self, body: CharacterBody, cid: str | None = None) -> dict:
        from .tenancy import ResourceLimit
        uid, now = owner(), time.time()
        refs = [r.model_dump() for r in body.references]
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            for ref in refs:
                row = db.execute("SELECT kind,sha256 FROM artifacts WHERE uri=? AND owner_id=?", (ref["uri"], uid)).fetchone()
                if not row or row["sha256"] != ref["sha256"].lower():
                    raise NotOwned("resource not found")
                if row["kind"] not in IMAGE_KINDS:
                    raise ValueError("Las referencias de un personaje deben ser imágenes")
            if body.lora_id and not db.execute("SELECT 1 FROM loras WHERE id=? AND owner_id=?", (body.lora_id, uid)).fetchone():
                raise NotOwned("resource not found")
            clash = db.execute("SELECT id FROM characters WHERE owner_id=? AND handle=?", (uid, body.handle)).fetchone()
            if clash and clash[0] != cid:
                raise ValueError(f"Ya tienes un personaje @{body.handle}")
            values = (body.handle, body.name.strip(), body.description.strip(), json.dumps(refs), body.lora_id, now)
            if cid:
                if not db.execute("UPDATE characters SET handle=?,name=?,description=?,references_json=?,lora_id=?,updated_at=? "
                                  "WHERE id=? AND owner_id=?", (*values, cid, uid)).rowcount:
                    raise NotOwned("resource not found")
            else:
                if db.execute("SELECT COUNT(*) FROM characters WHERE owner_id=?", (uid,)).fetchone()[0] >= CHARACTER_LIMIT:
                    raise ResourceLimit(f"Máximo {CHARACTER_LIMIT} personajes por cuenta")
                cid = "char_" + secrets.token_hex(8)
                db.execute("INSERT INTO characters(handle,name,description,references_json,lora_id,updated_at,id,owner_id,created_at) "
                           "VALUES(?,?,?,?,?,?,?,?,?)", (*values, cid, uid, now))
        return self.get(cid)

    def delete(self, cid: str) -> None:
        with self.store._db() as db:
            if not db.execute("DELETE FROM characters WHERE id=? AND owner_id=?", (cid, owner())).rowcount:
                raise NotOwned("resource not found")
