# -*- coding: utf-8 -*-
# pyright: strict
import hashlib
import os
import time
import uuid
from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
from typing import AsyncGenerator, Generator, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

DATABASE_URL = getenv("DATABASE_URL", "sqlite:///data/kosync.db")

if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:///:memory"):
    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    if db_path and not db_path.startswith("/"):
        db_path = Path.cwd() / db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)


class Document(Base):
    __tablename__ = "documents"

    username: Mapped[str] = mapped_column(String(255), ForeignKey("users.username"), primary_key=True)
    document: Mapped[str] = mapped_column(String(255), primary_key=True)
    progress: Mapped[str] = mapped_column(String(255), nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    device: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


app = FastAPI(openapi_url=None, redoc_url=None, lifespan=lifespan)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class KosyncUser(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None


class KosyncDocument(BaseModel):
    document: Optional[str] = None
    progress: Optional[str] = None
    percentage: Optional[float] = None
    device: Optional[str] = None
    device_id: Optional[str] = None


def hash_password(value: str) -> str:
    salt = hashlib.sha256(os.urandom(32)).hexdigest().encode("utf-8")
    dk = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, 200_000)
    return f"{salt.decode('utf-8')}:{dk.hex()}"


def verify_password(stored_hash: str, supplied_password: str) -> bool:
    if not stored_hash or ":" not in stored_hash:
        return False

    salt_hex, digest_hex = stored_hash.split(":", 1)
    if len(salt_hex) != 64:
        return False

    salt = salt_hex.encode("utf-8")
    expected = hashlib.pbkdf2_hmac("sha256", supplied_password.encode("utf-8"), salt, 200_000).hex()
    return expected == digest_hex


def strtobool(value: str) -> bool:
    value = value.lower()
    if value in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif value in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError(f"Invalid truth value: {value}")

@app.post("/users/create")
def register(kosync_user: KosyncUser, db: Session = Depends(get_db)):
    registrations_allowed = bool(strtobool(getenv("OPEN_REGISTRATIONS", "True")))
    if registrations_allowed:
        if kosync_user.username is None or kosync_user.password is None:
            return JSONResponse(status_code=400, content={"message": "Invalid request"})

        existing_user = db.get(User, kosync_user.username)
        if existing_user is not None:
            return JSONResponse(status_code=409, content="Username is already registered.")

        password_hash = hash_password(kosync_user.password)
        db.add(User(username=kosync_user.username, password=password_hash))
        db.commit()
        return JSONResponse(status_code=201, content={"username": kosync_user.username})

    return JSONResponse(status_code=403, content="This server is currently not accepting new registrations.")


@app.get("/users/auth")
def authorize(
    x_auth_user: Optional[str] = Header(None),
    x_auth_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_auth_user is None or x_auth_key is None:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    user = db.get(User, x_auth_user)
    if user is None:
        return JSONResponse(status_code=403, content={"message": "Forbidden"})

    if verify_password(user.password, x_auth_key):
        return JSONResponse(status_code=200, content={"authorized": "OK"})

    return JSONResponse(status_code=401, content={"message": "Unauthorized"})


@app.put("/syncs/progress")
def update_progress(
    kosync_document: KosyncDocument,
    x_auth_user: Optional[str] = Header(None),
    x_auth_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_auth_user is None or x_auth_key is None:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    user = db.get(User, x_auth_user)
    if user is None:
        return JSONResponse(status_code=403, content={"message": "Forbidden"})

    if not verify_password(user.password, x_auth_key):
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    timestamp = int(time.time())
    if (
        kosync_document.document is None
        or kosync_document.progress is None
        or kosync_document.percentage is None
        or kosync_document.device is None
        or kosync_document.device_id is None
    ):
        return JSONResponse(status_code=500, content="Unknown server error")

    db.merge(
        Document(
            username=x_auth_user,
            document=kosync_document.document,
            progress=kosync_document.progress,
            percentage=kosync_document.percentage,
            device=kosync_document.device,
            device_id=kosync_document.device_id,
            timestamp=timestamp,
        )
    )
    db.commit()
    return JSONResponse(status_code=200, content={"document": kosync_document.document, "timestamp": timestamp})


@app.get("/syncs/progress/{document}")
def get_progress(
    document: Optional[str] = None,
    x_auth_user: Optional[str] = Header(None),
    x_auth_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_auth_user is None or x_auth_key is None:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})
    if document is None:
        return JSONResponse(status_code=500, content="Unknown server error")

    user = db.get(User, x_auth_user)
    if user is None:
        return JSONResponse(status_code=403, content={"message": "Forbidden"})

    if not verify_password(user.password, x_auth_key):
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    result = (
        db.query(Document)
        .filter(Document.username == x_auth_user, Document.document == document)
        .one_or_none()
    )
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Document progress not found"})

    rrdi = bool(strtobool(getenv("RECEIVE_RANDOM_DEVICE_ID", "False")))
    if rrdi is False:
        device_id = result.device_id
    else:
        device_id = str(uuid.uuid1().hex).upper()

    return JSONResponse(
        status_code=200,
        content={
            "username": x_auth_user,
            "document": result.document,
            "progress": result.progress,
            "percentage": result.percentage,
            "device": result.device,
            "device_id": device_id,
            "timestamp": result.timestamp,
        },
    )


@app.get("/healthstatus")
def get_healthstatus():
    return JSONResponse(status_code=200, content={"message": "healthy"})
