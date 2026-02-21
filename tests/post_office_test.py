# Copyright 2026 John Hanley. MIT licensed.

import unittest

from db.post_office import get_nearby_post_offices, populate_table


class PostOfficeTest(unittest.TestCase):
    def test_nearby_post_offices(self) -> None:
        populate_table()
        self.assertEqual([], get_nearby_post_offices())
