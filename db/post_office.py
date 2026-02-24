# Copyright 2026 John Hanley. MIT licensed.

import os
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uszipcode as uszip
from sqlalchemy import BLOB, Column, Engine, Float, Integer, MetaData, String, create_engine, text
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
        raw = _engine.raw_connection()
        raw.enable_load_extension(True)
        raw.load_extension(os.environ["SPATIALITE_LIBRARY_PATH"])
        # conn.execute(text("PRAGMA load_extension('mod_spatialite')"))
        raw.close()

    return _engine


@contextmanager
def get_session() -> Generator[Session]:
    with sessionmaker(bind=get_engine())() as sess:
        try:
            yield sess
        finally:
            sess.commit()


WGS84 = 4326  # EPSG spatial reference system

Base = declarative_base()


class PostOffice(Base):
    __tablename__ = "post_office"

    zip = Column(String(5), primary_key=True)
    city = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    pop = Column(Integer, nullable=False)
    geom = Column(BLOB)
    # geom = Column(Geometry("POINT", WGS84))


def has_geom_column(table_name: str, sess: Session, verbose: bool = False) -> bool:
    meta = MetaData()
    meta.reflect(bind=get_engine())
    post_office_table = meta.tables[table_name]
    for column in post_office_table.columns:
        if column.name == "geom":
            if verbose:
                print(column.name.ljust(6), column.type)
            return "geometry(POINT,4326)" == f"{column.type}"
    return False


def populate_table() -> None:
    MetaData().create_all(get_engine(), tables=[PostOffice.__table__])
    search = uszip.SearchEngine()

    def execute(sql: str) -> None:
        sess.execute(text(sql))
        sess.commit()

    with get_session() as sess:
        sess.query(PostOffice).delete()
        if not has_geom_column("post_office", sess):
            execute("ALTER TABLE post_office  DROP COLUMN geom")
            execute("SELECT AddGeometryColumn('post_office', 'geom', 4326, 'POINT', 'XY')")
            execute("SELECT CreateSpatialIndex('post_office', 'geom')")

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
                    # geom=WKTElement(f"POINT({r.lng} {r.lat})"),
                )
                sess.add(po)

        sess.commit()
        update = text("""
            UPDATE post_office
            SET geom = ST_GeomFromText(CONCAT('POINT(', lng, ' ', lat, ')'), 4326)
        """)
        sess.execute(update)
        sess.commit()
        # last row is ZIP 02113, at (42.37 -71.06)


@dataclass
class Location:
    lat: float
    lng: float

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, (Location, tuple)):
            return False
        if isinstance(other, tuple) and len(other) != 2:
            return False
        oth = other if isinstance(other, Location) else Location(*other)
        return (self.lat, self.lng) == (oth.lat, oth.lng)


def get_nearby_post_offices(lat: float, lng: float, limit: int = 3) -> list[Location]:
    with get_session() as sess:
        point = f"POINT({lng} {lat})"
        select = text("""
            SELECT lat, lng
            FROM post_office
            ORDER BY ST_Distance(geom, ST_GeomFromText(:point)) ASC
            LIMIT :k;
        """)
        q = sess.execute(select, {"point": point, "k": limit})
        return [Location(float(row.lat), float(row.lng)) for row in q]
