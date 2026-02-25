# Copyright 2026 John Hanley. MIT licensed.

import unittest

from db.battle_bus import BattleBusPair, Battlefield


class BattleBusTest(unittest.TestCase):
    def test_battlefield(self) -> None:
        bf = Battlefield()
        bbus = BattleBusPair()
        bbus.distribute(bf)

        bf.frame()
        bf.display()
