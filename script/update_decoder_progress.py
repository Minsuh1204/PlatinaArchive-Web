import os.path
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app import app
from models import Decoder, DecoderProgress, db

sys.path.insert(0, os.path.dirname((os.path.abspath(__file__))))


def get_all_decoder() -> list[Decoder]:
    return db.execute(select(Decoder)).scalars().all()


def update_decoder_progress(decoder: Decoder):
    current_4l_total = decoder.get_top_50_patch_sum(4, False)
    current_4l_plus_total = decoder.get_top_50_patch_sum(4, True)
    current_6l_total = decoder.get_top_50_patch_sum(6, False)
    current_6l_plus_total = decoder.get_top_50_patch_sum(6, True)
    db_4l = DecoderProgress.get_latest_progress(decoder.name, "4L")
    db_4l_plus = DecoderProgress.get_latest_progress(decoder.name, "4L+")
    db_6l = DecoderProgress.get_latest_progress(decoder.name, "6L")
    db_6l_plus = DecoderProgress.get_latest_progress(decoder.name, "6L+")

    needs_update = False

    if db_4l is None or db_4l.total < current_4l_total:
        db_4l = DecoderProgress(
            decoder=decoder.name,
            line="4L",
            total=current_4l_total,
            recorded_at=datetime.now(timezone.utc),
        )
        db.session.add(db_4l)
        needs_update = True

    if db_4l_plus is None or db_4l_plus.total < current_4l_plus_total:
        db_4l_plus = DecoderProgress(
            decoder=decoder.name,
            line="4L+",
            total=current_4l_plus_total,
            recorded_at=datetime.now(timezone.utc),
        )
        db.session.add(db_4l_plus)
        needs_update = True

    if db_6l is None or db_6l.total < current_6l_total:
        db_6l = DecoderProgress(
            decoder=decoder.name,
            line="6L",
            total=current_6l_total,
            recorded_at=datetime.now(timezone.utc),
        )
        db.session.add(db_6l)
        needs_update = True

    if db_6l_plus is None or db_6l_plus.total < current_6l_plus_total:
        db_6l_plus = DecoderProgress(
            decoder=decoder.name,
            line="6L+",
            total=current_6l_plus_total,
            recorded_at=datetime.now(timezone.utc),
        )
        db.session.add(db_6l_plus)
        needs_update = True

    if needs_update:
        db.session.commit()


if __name__ == "__main__":
    with app.app_context():
        decoders = get_all_decoder()
        for decoder in decoders:
            update_decoder_progress(decoder)
