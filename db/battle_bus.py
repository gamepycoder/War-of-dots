# Copyright 2026 John Hanley. MIT licensed.

"""
This module's simplified battlefield lets us explore Troop scaling.

Combat models want to know "what troops are near which other ones?"
A typical implementation compares all-to-all distances,
leading to N ** 2 quadratic scaling.
Quadtrees offer better scaling, assuming that troops don't form giant clumps.

Popular quadtree spatial indexes include:
- PostGIS for postgres
- Spatialite for sqlite

A pair of battle buses fly over the battlefield,
distributing Red and Blue troops in two vertical swaths.
The battlefield is a unit square.
Red flies north along the western border; Blue south along the eastern one.
At the start of Phase 1, troops land within +/- 0.1 of the bus flight path.

Red troops then proceed due east, and Blue troops due west.
We either move, or shoot.
If an enemy is within range, the troop stays put and fires on them.
The Middle Zone extends over the x range 0.4 .. 0.6.

Phase 2:
Any troop that crosses x == 0.5 and then exits the Middle Zone
will change direction so it heads directly for the Center at (0.5, 0.5).

Eliminate all enemy troops to win.
"""

import math
import os
from enum import Enum
from pathlib import Path
from random import seed, uniform

import matplotlib.pyplot as plt
from sqlalchemy import Column, Float, Integer, create_engine, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from wod_server import dir_dis_to_xy


class BFPlayer(Enum):
    RED = 0
    BLUE = 1


Base = declarative_base()


class BFTroop(Base):  # type: ignore
    __tablename__ = "bftroop"

    serial = Column(Integer, primary_key=True)  # "Name, rank, and serial number, please."
    player = Column(Integer)  # BFPlayer.{RED,BLUE}
    x = Column(Float)
    y = Column(Float)
    health = Column(Integer)  # 100 is fully healthy


class Battlefield:
    """Troops move upon a Battlefield, which is persisted in an RDBMS."""

    def __init__(self, want_db_echo: bool = False) -> None:
        db_file = Path("/tmp/battlefield.db")
        db_url = f"sqlite:///{db_file}"
        self.engine = create_engine(db_url, echo=want_db_echo, plugins=["geoalchemy2"])

        raw = self.engine.raw_connection()
        raw.enable_load_extension(True)
        raw.load_extension(os.environ["SPATIALITE_LIBRARY_PATH"])
        raw.close()

        self._create_tables()

    def get_session(self) -> Session:
        return sessionmaker(bind=self.engine)()

    def _create_tables(self) -> None:

        Base.metadata.create_all(self.engine)

        with self.get_session() as sess:
            sess.query(BFTroop).delete()
            sess.commit()

    def frame(self) -> bool:
        """Advance the simulation by one display frame.

        All soldiers either move by the same tiny distance, or they shoot.
        Returns True while both sides still have troops, False in the case of victory.
        """

        return True

    def display(self) -> None:
        with self.get_session() as sess:
            red_troops = sess.query(BFTroop).filter_by(player=BFPlayer.RED.value).all()
            blue_troops = sess.query(BFTroop).filter_by(player=BFPlayer.BLUE.value).all()

            if red_troops:
                red_x = [troop.x for troop in red_troops]
                red_y = [troop.y for troop in red_troops]
            else:
                red_x, red_y = [], []

            if blue_troops:
                blue_x = [troop.x for troop in blue_troops]
                blue_y = [troop.y for troop in blue_troops]
            else:
                blue_x, blue_y = [], []

        plt.figure(figsize=(6, 6))
        plt.title("Battlefield Troop Positions")
        # plt.xlim(0, 1)
        # plt.ylim(0, 1)

        if red_x and red_y:  # Ensure there are coordinates to plot
            plt.scatter(red_x, red_y, color="red", label="Red")

        if blue_x and blue_y:
            plt.scatter(blue_x, blue_y, color="blue", label="Blue")

        plt.xlabel("X Position")
        plt.ylabel("Y Position")
        plt.legend(loc="upper right")
        plt.grid(True)
        plt.show()


class BattleBusPair:
    """
    A pair of buses produce the initial distribution of troops on the battlefield.

    Red flies north in the west, while Blue flies along the eastern border.
    Each produces a swath of soldiers that is 0.2 wide.
    """

    def __init__(self, num_troops: int = 100) -> None:
        serial = 0
        x_red = 0.2
        x_blue = 0.8
        self.troops: list[BFTroop] = []
        for _ in range(num_troops):
            self.troops.append(
                BFTroop(serial=serial, player=BFPlayer.BLUE, x=x_blue, y=0.0),
            )
            serial += 1
            self.troops.append(
                BFTroop(serial=serial, player=BFPlayer.RED, x=x_red, y=0.0),
            )
            serial += 1

    def _pop(self, player_color: BFPlayer, y: float) -> BFTroop:
        troop = self.troops.pop()
        # assert troop.player == player_color
        return BFTroop(
            serial=troop.serial,
            player=troop.player,
            x=troop.x,
            y=y,
            health=troop.health,
        )

    def _insert(self, troop: BFTroop, session: Session) -> None:
        session.add(
            BFTroop(
                serial=troop.serial,
                player=troop.player,
                x=func.round(troop.x, 6),
                y=func.round(troop.y, 6),
                health=troop.health,
            )
        )

    def _pick_random_heading(self, troop: BFTroop, distance: float = 0.1) -> BFTroop:
        """This produces a swath of soldiers, of width 0.2."""
        direc = math.radians(uniform(0.0, 360.0))
        x, y = dir_dis_to_xy(direc, distance)
        return BFTroop(
            serial=troop.serial,
            player=troop.player.value,
            x=x,
            y=y,
            health=troop.health,
        )

    def distribute(self, bf: Battlefield) -> None:
        """
        Fly over the battlefield, dropping troops as we go.
        """
        seed(42)
        y = 0.1  # This always reflects the current bus location.
        num_troops = len(self.troops) / 2
        dy = (0.9 - y) / num_troops
        with bf.get_session() as sess:
            while self.troops:
                y += dy  # Fly north one increment.
                for color in (BFPlayer.RED, BFPlayer.BLUE):
                    troop = self._pop(color, y=y)
                    troop = self._pick_random_heading(troop)
                    self._insert(troop, sess)

            sess.commit()
