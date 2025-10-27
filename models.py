from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
from typing import Literal, TypedDict

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, desc, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

# Load .env
BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv()

type Lines = Literal[4, 6]
type Difficulties = Literal["EASY", "HARD", "OVER", "PLUS"]
type DecoderEmblem = Literal[
    "bit",
    "nibble",
    "Byte",
    "deca",
    "hecto",
    "kilo",
    "Mega",
    "Giga",
    "Tera",
    "Peta",
    "Exa",
    "Zeta",
    "Yotta",
]  # These names are from SI byte units


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class DecoderProgress(db.Model):
    __tablename__ = "DecoderProgress"

    decoder: Mapped[str] = mapped_column(
        "decoder", ForeignKey("Decoders.name"), primary_key=True
    )
    line: Mapped[str] = mapped_column("line", primary_key=True)
    total: Mapped[float] = mapped_column("total")
    recorded_at: Mapped[datetime] = mapped_column("recorded_at", primary_key=True)
    decoder_obj: Mapped[Decoder] = relationship(back_populates="progresses")

    @classmethod
    def get_latest_progress(
        cls, decoder: str, line: Literal["4L", "4L+", "6L", "6L+"]
    ) -> DecoderProgress | None:
        return db.session.execute(
            select(cls)
            .filter(DecoderProgress.decoder == decoder, DecoderProgress.line == line)
            .order_by(desc(cls.recorded_at))
        ).scalar()


class DecoderStatus(TypedDict):
    decoder: str
    line: Lines
    is_plus: bool
    total_patterns: int
    cleared_patterns: int
    full_combo_patterns: int
    perfect_decode_patterns: int
    max_patch_patterns: int


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

    @classmethod
    def from_song_id(cls, song_id: int):
        return db.session.get(PlatinaSong, song_id)


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
    progresses: Mapped[list[DecoderProgress]] = relationship(
        back_populates="decoder_obj"
    )

    def calculate_emblem(
        self, line: Lines, is_plus: bool
    ) -> tuple[float, DecoderEmblem]:
        total_patch = sum(
            result.patch for result in self.get_top_50_patch_results(line, is_plus)
        )
        if total_patch < 5000:
            emblem = "bit"
        elif total_patch < 10000:
            emblem = "nibble"
        elif total_patch < 15000:
            emblem = "Byte"
        elif total_patch < 20000:
            emblem = "deca"
        elif total_patch < 25000:
            emblem = "hecto"
        elif total_patch < 30000:
            emblem = "kilo"
        elif total_patch < 35000:
            emblem = "Mega"
        elif total_patch < 40000:
            emblem = "Giga"
        elif total_patch < 45000:
            emblem = "Tera"
        elif total_patch < 50000:
            emblem = "Peta"
        elif total_patch < 55000:
            emblem = "Exa"
        elif total_patch < 60000:
            emblem = "Zeta"
        else:
            emblem = "Yotta"
        return total_patch, emblem

    def get_top_50_patch_sum(self, line: Lines, is_plus: bool) -> float:
        return sum(r.patch for r in self.get_top_50_patch_results(line, is_plus))

    def get_top_50_patch_results(
        self, line: Lines, is_plus: bool
    ) -> list[DecodeResult]:
        """Get top 50 plays by P.A.T.C.H. value for a specific line and PLUS mode."""
        # Determine difficulty filter
        difficulty_filter = (
            DecodeResult.difficulty == "PLUS"
            if is_plus
            else DecodeResult.difficulty != "PLUS"
        )

        return (
            db.session.execute(
                select(DecodeResult)
                .filter(
                    DecodeResult.decoder == self.name,
                    DecodeResult.line == line,
                    difficulty_filter,
                )
                .order_by(desc(DecodeResult.patch))
                .limit(50)
            )
            .scalars()
            .all()
        )

    def get_status(self, line: Lines, is_plus: bool) -> DecoderStatus:
        """
        Get number of patterns cleared, full combo, perfect and max patch and total patterns \n
        for a specific line and PLUS mode.
        """
        result_difficulty_filter = (
            DecodeResult.difficulty == "PLUS"
            if is_plus
            else DecodeResult.difficulty != "PLUS"
        )
        pattern_difficulty_filter = (
            PlatinaPattern.difficulty == "PLUS"
            if is_plus
            else PlatinaPattern.difficulty != "PLUS"
        )
        cleared_patterns_select = (
            select(func.count())
            .select_from(DecodeResult)
            .filter(
                DecodeResult.decoder == self.name,
                DecodeResult.line == line,
                result_difficulty_filter,
            )
        )
        total_patterns = db.session.scalar(
            select(func.count())
            .select_from(PlatinaPattern)
            .filter(
                PlatinaPattern.line == line,
                pattern_difficulty_filter,
            )
        )
        cleared_patterns = db.session.scalar(cleared_patterns_select)
        full_combo_patterns = db.session.scalar(
            cleared_patterns_select.filter(
                DecodeResult.decoder == self.name, DecodeResult.is_full_combo
            )
        )
        perfect_decode_patterns = db.session.scalar(
            cleared_patterns_select.filter(
                DecodeResult.decoder == self.name, DecodeResult.judge == 100
            )
        )
        max_patch_patterns = db.session.scalar(
            cleared_patterns_select.filter(
                DecodeResult.decoder == self.name, DecodeResult.is_max_patch
            )
        )
        return {
            "decoder": str(self.name),
            "line": line,
            "is_plus": is_plus,
            "total_patterns": total_patterns,
            "cleared_patterns": cleared_patterns,
            "full_combo_patterns": full_combo_patterns,
            "perfect_decode_patterns": perfect_decode_patterns,
            "max_patch_patterns": max_patch_patterns,
        }

    def check_pass(self, password: str):
        return check_password_hash(self.hashed_pass, password)

    @staticmethod
    def is_name_available(name: str):
        return not db.session.get(Decoder, name)

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
        decoder = db.session.get(Decoder, name)
        if not decoder:
            return None
        given_hash = sha256(given_secret.encode()).hexdigest()
        if compare_digest(given_hash, decoder.hashed_secret):
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
    old_judge: Mapped[float] = mapped_column("oldJudge")
    old_score: Mapped[int] = mapped_column("oldScore")
    old_patch: Mapped[float] = mapped_column("oldPatch")
    old_is_full_combo: Mapped[bool] = mapped_column("oldIsFullCombo")
    old_is_max_patch: Mapped[bool] = mapped_column("oldIsMaxPatch")
    # relations
    decoder_obj: Mapped[Decoder] = relationship(back_populates="decode_results")
    song: Mapped[PlatinaSong] = relationship(back_populates="decode_results")

    @staticmethod
    def get_archive(decoder: str):
        return (
            db.session.execute(select(DecodeResult).filter_by(decoder=decoder))
            .scalars()
            .all()
        )

    @staticmethod
    def update_or_make(
        decoder: str,
        song_id: int,
        line: Lines,
        difficulty: Difficulties,
        level: int,
        new_judge: float,
        new_score: int,
        new_patch: float,
        new_is_full_combo: bool,
        new_is_max_patch: bool,
    ):
        existing_archive = db.session.get(
            DecodeResult, (decoder, song_id, line, difficulty, level)
        )
        utc_now = datetime.now(timezone.utc)
        if not existing_archive:
            # There is no existing archive
            new_archive = DecodeResult(
                decoder=decoder,
                song_id=song_id,
                line=line,
                difficulty=difficulty,
                level=level,
                judge=new_judge,
                score=new_score,
                patch=new_patch,
                decoded_at=utc_now,
                is_full_combo=new_is_full_combo,
                is_max_patch=new_is_max_patch,
                old_judge=0.0,
                old_score=0,
                old_patch=0.0,
                old_is_full_combo=False,
                old_is_max_patch=False,
            )
            db.session.add(new_archive)
        else:
            # Existing archive needs update
            existing_archive.old_judge = existing_archive.judge
            existing_archive.old_score = existing_archive.score
            existing_archive.old_patch = existing_archive.patch
            existing_archive.old_is_full_combo = existing_archive.is_full_combo
            existing_archive.old_is_max_patch = existing_archive.is_max_patch
            existing_archive.decoded_at = utc_now
            existing_archive.judge = new_judge
            existing_archive.score = new_score
            existing_archive.patch = new_patch
            existing_archive.is_full_combo = new_is_full_combo
            existing_archive.is_max_patch = new_is_max_patch
            db.session.add(existing_archive)
        try:
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False
