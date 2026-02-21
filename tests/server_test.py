# Copyright 2026 John Hanley. MIT licensed.

import unittest

from wod_server import xy_to_dir_dis


class ServerTest(unittest.TestCase):

    def test_cartesian_to_polar(self) -> None:
        direc, dist = xy_to_dir_dis((3.0, 4.0))
        self.assertEqual(53.13, round(direc, 2))  # degrees, not radians
        self.assertEqual(5.0, dist)
