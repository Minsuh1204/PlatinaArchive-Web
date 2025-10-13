from __future__ import annotations

import os
import secrets
from datetime import datetime
from hashlib import sha256
from typing import Literal

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

# Load .env
BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv()

Lines = Literal[4, 6]
Difficulties = Literal["EASY", "HARD", "OVER", "PLUS"]


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
    # relations
    patterns: Mapped[list[PlatinaPattern]] = relationship(back_populates="song")
    decode_results: Mapped[list[DecodeResult]] = relationship(back_populates="song")

    @staticmethod
    def get_all() -> list[PlatinaSong]:
        return db.session.execute(db.select(PlatinaSong)).scalars().all()

    def get_available_levels(self, line: Lines, difficulty: Difficulties) -> list[int]:
        return [
            ptn.level
            for ptn in self.patterns
            if ptn.line == line and ptn.difficulty == difficulty
        ]


class PlatinaPattern(db.Model):
    __tablename__ = "PlatinaPatterns"

    song_id: Mapped[int] = mapped_column(
        "songID", ForeignKey("PlatinaSongs.songID"), primary_key=True
    )
    line: Mapped[int] = mapped_column("line", primary_key=True)
    difficulty: Mapped[str] = mapped_column("difficulty", primary_key=True)
    level: Mapped[int] = mapped_column("level", primary_key=True)
    designer: Mapped[str] = mapped_column("designer")
    # relation
    song: Mapped[PlatinaSong] = relationship(back_populates="patterns")

    @staticmethod
    def get_all() -> list[PlatinaPattern]:
        return db.session.execute(db.select(PlatinaPattern)).scalars().all()


class Decoder(db.Model):
    __tablename__ = "Decoders"

    name: Mapped[str] = mapped_column("name", primary_key=True)
    hashed_secret: Mapped[str] = mapped_column("hashedSecret")
    # The key will be stored in client as they first register/login
    hashed_pass: Mapped[str] = mapped_column("hashedPass")
    # relation
    decode_results: Mapped[list[DecodeResult]] = relationship(
        back_populates="decoder_obj"
    )

    def check_pass(self, password: str):
        return check_password_hash(self.hashed_pass, password)

    @staticmethod
    def is_name_available(name: str):
        return not Decoder.query.filter_by(name=name).one_or_none()

    @classmethod
    def register(cls, name: str, password: str) -> tuple[Decoder, str] | None:
        if not cls.is_name_available(name):
            return None

        # API Key structure: name::secret
        secret = secrets.token_urlsafe(64)
        key = f"{name}::{secret}"
        hashed_secret = sha256(secret.encode()).hexdigest()
        hashed_pass = generate_password_hash(password)
        decoder = cls(name=name, hashed_secret=hashed_secret, hashed_pass=hashed_pass)
        db.session.add(decoder)
        db.session.commit()
        return decoder, key

    @staticmethod
    def load_by_key(key: str) -> Decoder | None:
        name, given_secret = key.split("::")
        decoder = Decoder.query.filter_by(name=name).one_or_none()
        if not decoder:
            return None
        if sha256(given_secret.encode()).hexdigest() == decoder.hashed_secret:
            return decoder
        else:
            return None


class DecodeResult(db.Model):
    __tablename__ = "DecodeResults"

    decoder: Mapped[str] = mapped_column(
        "decoder", ForeignKey("Decoders.name"), primary_key=True
    )
    song_id: Mapped[int] = mapped_column(
        "songID", ForeignKey("PlatinaSongs.songID"), primary_key=True
    )
    line: Mapped[int] = mapped_column("line", primary_key=True)
    difficulty: Mapped[str] = mapped_column("difficulty", primary_key=True)
    level: Mapped[int] = mapped_column("level", primary_key=True)
    judge: Mapped[float] = mapped_column("judge")
    score: Mapped[int] = mapped_column("score")
    patch: Mapped[float] = mapped_column("patch")
    decoded_at: Mapped[datetime] = mapped_column("decodedAt")
    is_full_combo: Mapped[bool] = mapped_column("isFullCombo")
    is_max_patch: Mapped[bool] = mapped_column("isMaxPatch")
    # relations
    decoder_obj: Mapped[Decoder] = relationship(back_populates="decode_results")
    song: Mapped[PlatinaSong] = relationship(back_populates="decode_results")

    @staticmethod
    def get_archive(decoder: str):
        return DecodeResult.query.filter_by(decoder=decoder).all()
