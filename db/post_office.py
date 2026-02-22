# Copyright 2026 John Hanley. MIT licensed.

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import uszipcode as uszip
from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import Column, Engine, Float, Integer, MetaData, String, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from uszipcode import ZipcodeTypeEnum as ZipType

_engine = None


def get_engine(want_echo: bool = False) -> Engine:
    """Connects to a spatial sqlite RDBMS in /tmp.

    Install spatial support on MacOS using:
    brew install spatialite-tools"""
    global _engine
    if not _engine:
        DB_FILE = Path("/tmp/dots.db")
        DB_URL = f"sqlite:///{DB_FILE}"
        _engine = create_engine(DB_URL, echo=want_echo, plugins=["geoalchemy2"])
        with _engine.connect() as conn:

            select = """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='spatial_ref_sys'
                """
            raw = _engine.raw_connection()
            raw.enable_load_extension(True)
            raw.execute("PRAGMA load_extension('mod_spatialite')")
            raw.load_extension("/opt/homebrew/lib/mod_spatialite")
            if not conn.execute(text(select)).fetchone():
                cursor = raw.cursor()
                cursor.execute("SELECT InitSpatialMetaData()")
            raw.commit()
            raw.close()

        with _engine.connect() as conn:
            conn.execute(text("PRAGMA load_extension('mod_spatialite');"))

    return _engine


@contextmanager
def get_session() -> Generator[Session]:
    with sessionmaker(bind=get_engine())() as sess:

        sess.query(text("PRAGMA load_extension('mod_spatial');"))

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
    geom = Column(Geometry("POINT"), nullable=False)


WGS84 = 4326  # EPSG spatial reference system


def populate_table() -> None:
    MetaData().create_all(get_engine(), tables=[PostOffice.__table__])

    search = uszip.SearchEngine()
    with get_session() as sess:
        sess.query(PostOffice).delete()
        sess.query(text("PRAGMA load_extension('mod_spatial');"))

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
                    geom=WKTElement(f"POINT({r.lng} {r.lat})"),
                )
                sess.add(po)
        sess.commit()
        # last row is ZIP 02113, at (42.37 -71.06)

    def create_spatial_index() -> None:
        with get_engine().connect() as conn:
            conn.execute(text("CREATE SPATIAL INDEX idx_geom ON post_office(geom);"))


def get_nearby_post_offices(lat: float, lng: float, k: int = 3) -> list[tuple[float, float]]:
    with get_session() as sess:
        point = f"POINT({lng} {lat})"
        select = text("""
            SELECT lat, lng
            FROM post_office
            ORDER BY ST_Distance(geom, GeomFromText(:point)) ASC
            LIMIT :k;
        """)
        q = sess.execute(select, {"point": point, "k": k})
        return [(float(row.lat), float(row.lng)) for row in q]
