from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import os
import secrets

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from werkzeug.security import generate_password_hash, check_password_hash


# Load .env
BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv()


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
    hashed_secret: Mapped[str] = mapped_column("hashedSecret")
    # The key will be stored in client as they first register/login
    hashed_pass: Mapped[str] = mapped_column("hashedPass")

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

    decoder: Mapped[str] = mapped_column("decoder", primary_key=True)
    song_id: Mapped[int] = mapped_column("songID", primary_key=True)
    line: Mapped[int] = mapped_column("line", primary_key=True)
    difficulty: Mapped[str] = mapped_column("difficulty", primary_key=True)
    level: Mapped[int] = mapped_column("level", primary_key=True)
    judge: Mapped[float] = mapped_column("judge")
    score: Mapped[int] = mapped_column("score")
    patch: Mapped[float] = mapped_column("patch")
    date_decoded: Mapped[datetime] = mapped_column("dateDecoded")

    @staticmethod
    def update(
        decoder: str,
        song_id: int,
        line: int,
        difficulty: str,
        level: int,
        judge: float,
        score: int,
        patch: float,
        date_decoded: datetime,
    ) -> tuple[bool, float, int, datetime] | tuple[bool, float, int, float]:
        db_updated = False
        existing_record = DecodeResult.query.get(
            (decoder, song_id, line, difficulty, level)
        )
        if not existing_record:
            new_record = DecodeResult(
                decoder=decoder,
                song_id=song_id,
                line=line,
                difficulty=difficulty,
                level=level,
                judge=judge,
                score=score,
                patch=patch,
                date_decoded=date_decoded,
            )
            db.session.add(new_record)
            db_updated = True

        elif judge > existing_record.judge or (
            judge == existing_record.judge and score > existing_record.score
        ):
            old_judge = existing_record.judge
            old_score = existing_record.score
            old_patch = existing_record.patch

            # Update the existing record in place
            existing_record.judge = judge
            existing_record.score = score
            existing_record.patch = patch
            existing_record.date_decoded = date_decoded
            db_updated = True

        if db_updated:
            db.session.commit()

        if db_updated:
            return (True, old_judge, old_score, old_patch)
        else:
            return (
                False,
                existing_record.judge,
                existing_record.score,
                existing_record.date_decoded,
            )
