from __future__ import annotations

import os
from hashlib import sha3_256

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, reconstructor


# Load .env
load_dotenv(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".env"))
SALT = os.getenv("SALT")


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class PlatinaSong(db.Model):
    __tablename__ = "PlatinaSongs"

    song_id: Mapped[int] = mapped_column("songID", autoincrement=True, primary_key=True)
    title: Mapped[str] = mapped_column("title")
    artist: Mapped[str] = mapped_column("artist")
    bpm: Mapped[str] = mapped_column("BPM")
    dlc: Mapped[str] = mapped_column("DLC")
    phash: Mapped[str] = mapped_column("pHash")
    plus_phash: Mapped[str] = mapped_column("plusPHash")

    @staticmethod
    def get_all() -> list[PlatinaSong]:
        return db.session.execute(db.select(PlatinaSong)).scalars().all()


class PlatinaPattern(db.Model):
    __tablename__ = "PlatinaPatterns"

    song_id: Mapped[int] = mapped_column("songID", primary_key=True)
    line: Mapped[int] = mapped_column("line", primary_key=True)
    difficulty: Mapped[str] = mapped_column("difficulty", primary_key=True)
    level: Mapped[int] = mapped_column("level", primary_key=True)
    designer: Mapped[str] = mapped_column("designer")

    @staticmethod
    def get_all() -> list[PlatinaPattern]:
        return db.session.execute(db.select(PlatinaPattern)).scalars().all()


class Decoder(db.Model):
    __tablename__ = "Decoders"

    name: Mapped[str] = mapped_column("name", primary_key=True)
    hashed_key: Mapped[str] = mapped_column("hashedKey")
    hashed_pass: Mapped[str] = mapped_column("hashedPass")
