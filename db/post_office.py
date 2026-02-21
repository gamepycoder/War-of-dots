# Copyright 2026 John Hanley. MIT licensed.

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import uszipcode as uszip
from sqlalchemy import Column, Engine, Float, Integer, MetaData, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from uszipcode import ZipcodeTypeEnum as ZipType

_engine = None


def get_engine() -> Engine:
    global _engine
    if not _engine:
        DB_FILE = Path("/tmp/dots.db")
        DB_URL = f"sqlite:///{DB_FILE}"
        _engine = create_engine(DB_URL)
    return _engine


@contextmanager
def get_session() -> Generator[Session]:
    with sessionmaker(bind=get_engine())() as sess:
        try:
            yield sess
        finally:
            sess.commit()


Base = declarative_base()


class PostOffice(Base):
    __tablename__ = "post_office"

    zip = Column(String(5), primary_key=True)
    city = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    pop = Column(Integer, nullable=False)


def populate_table() -> None:
    MetaData().create_all(get_engine(), tables=[PostOffice.__table__])

    search = uszip.SearchEngine()
    with get_session() as sess:
        sess.query(PostOffice).delete()

        for city_st in [
            ("Albany", "NY"),
            ("Boston", "MA"),
        ]:
            for r in search.by_city_and_state(*city_st, zipcode_type=ZipType.Standard):
                po = PostOffice(
                    zip=r.zipcode,
                    city=r.post_office_city,
                    lat=r.lat,
                    lng=r.lng,
                    pop=r.population,
                )
                sess.add(po)
        sess.commit()
        assert po.zip == "02113"
        print(po.lat, po.lng)


def get_nearby_post_offices(k: int = 3) -> str:
    with get_session() as sess:
        q = sess.query(PostOffice)
        for row in q:
            assert row.__dict__
    return ""
