# Copyright 2026 John Hanley. MIT licensed.

import unittest

from db.post_office import get_nearby_post_offices, populate_table


class PostOfficeTest(unittest.TestCase):
    def test_nearby_post_offices(self) -> None:
        populate_table()
        self.assertEqual(
            [(42.37, -71.06), (42.36, -71.06), (42.37, -71.05)],
            get_nearby_post_offices(42.371, -71.061),
        )
        self.assertEqual(
            [(42.69, -73.73), (42.67, -73.78)],
            get_nearby_post_offices(42.691, -73.731, limit=2),
        )
