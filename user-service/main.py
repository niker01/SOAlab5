import logging
import sqlite3
import threading
from typing import Optional

from fastapi import FastAPI, Header, HTTPException

from auth import install_cors, verify_authorization
from database import db_connection, enqueue_event, initialize_database
from observability import install_observability
from rabbitmq import publish_outbox_forever


app = FastAPI(title="User Service")
logger = logging.getLogger(__name__)
install_cors(app)
install_observability(app, "user-service")


@app.on_event("startup")
def startup_event():
    initialize_database()
    threading.Thread(target=publish_outbox_forever, daemon=True).start()


def _ensure_profile(claims: dict) -> dict:
    user_id = claims["sub"]
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise HTTPException(status_code=403, detail="The access token has no email claim")
    with db_connection() as connection:
        deleted = connection.execute(
            "SELECT 1 FROM deleted_users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if deleted is not None:
            raise HTTPException(status_code=410, detail="User profile was deleted")
        user = connection.execute(
            "SELECT id, email FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if user is None:
            email_owner = connection.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,)
            ).fetchone()
            if email_owner is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Email is already linked to a different local profile",
                )
            try:
                connection.execute(
                    "INSERT INTO users (id, email, password_hash) VALUES (?, ?, '')",
                    (user_id, email)
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Could not create the local user profile",
                ) from exc
        elif user["email"] != email:
            try:
                connection.execute(
                    "UPDATE users SET email = ? WHERE id = ?",
                    (email, user_id)
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Email is already linked to a different local profile",
                ) from exc
    return {"id": user_id, "email": email}


@app.get("/users", status_code=200)
def get_users(authorization: Optional[str] = Header(None)):
    claims = verify_authorization(authorization, ["users:read"])
    return [_ensure_profile(claims)]


@app.get("/users/{user_id}", status_code=200)
def get_user(user_id: str, authorization: Optional[str] = Header(None)):
    claims = verify_authorization(authorization, ["users:read"])
    if user_id != claims["sub"]:
        raise HTTPException(status_code=404, detail="User not found")
    return _ensure_profile(claims)


@app.delete("/users/{user_id}", status_code=200)
def delete_user(user_id: str, authorization: Optional[str] = Header(None)):
    claims = verify_authorization(authorization, ["users:write"])
    if user_id != claims["sub"]:
        raise HTTPException(status_code=404, detail="User not found")

    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute(
            "SELECT id FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        connection.execute(
            "INSERT OR IGNORE INTO deleted_users (user_id) VALUES (?)",
            (user_id,)
        )
        enqueue_event(
            connection,
            "user.deleted",
            {"event_type": "user.deleted", "user_id": user_id}
        )
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))

    return {"message": "User deleted successfully"}
