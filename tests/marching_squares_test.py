import unittest

import numpy as np

from constants import CELL_SIZE
from wod_server import City, Environment, MarchingSquares

albany = City((3 * CELL_SIZE, 4 * CELL_SIZE))
boston = City((5 * CELL_SIZE, 6 * CELL_SIZE))


class DeterministicEnvironment(Environment):
    def generate_terrain(self) -> None:

        self.cities += [albany, boston]
        f = self.forest_marching
        f.grid[3][4] = 0.92
        f.grid[4][4] = 0.96
        t = self.terrain_marching
        t.grid[3][4] = 0.91
        t.grid[4][4] = 0.95
        self.generate_default_vision()


class MarchingSquaresTest(unittest.TestCase):

    def test_get_grid_value(self) -> None:
        ms = MarchingSquares()
        self.assertAlmostEqual(0.0, ms.get_grid_value(5.0, 6.0))
        self.assertAlmostEqual(0.0, ms.get_grid_value(5.2, 6.2))

    def _check_marching(self, env: Environment) -> None:
        self.assertAlmostEqual(0.7424, env.forest_marching.get_grid_value(3.2, 4.2))

        self.assertAlmostEqual(0.7344, env.terrain_marching.get_grid_value(3.2, 4.2))

    def _check_vision(self, env: Environment) -> None:
        v = env.default_vision
        self.assertAlmostEqual(2.15, v[3][4])
        self.assertAlmostEqual(2.15, v[4][4])

        # It defaults to "poor visibility".
        self.assertAlmostEqual(0.65, v[5][4])
        self.assertAlmostEqual(0.65, v[0][0])

    def _check_draw(self, env: Environment) -> None:
        # We really should be getting back a DrawInfo @dataclass here.
        di = env.draw_info(player=0)  # vision_grid, border_grid, troops, cities
        self.assertEqual([], di[2])
        red, blue = 0, 1
        self.assertEqual(
            ((255, 0, 0), albany.position),  # (60, 80)
            di[3][red][:2],
        )
        self.assertEqual(
            ((0, 0, 255), boston.position),
            di[3][blue][:2],
        )

    def test_environment(self) -> None:

        env = DeterministicEnvironment()
        self.assertEqual(2, len(env.cities))
        self.assertEqual((60, 80), env.cities[0].position)

        self._check_marching(env)
        self._check_vision(env)
        self._check_draw(env)

    def test_brush_apply(self, verbose: bool = False) -> None:

        env = DeterministicEnvironment()
        br = env.city_vision_brush
        self.assertEqual(175, br.radius)
        self.assertEqual(1, br.strength)
        br.strength *= 1.5  # This conveniently saturates result values to 1.0.

        ter = env.terrain_marching
        old = np.array(ter.grid)

        br.apply(ter, albany.position, 42.0)

        new = np.array(ter.grid)
        self.assertFalse(np.array_equal(old, new))
        if verbose:
            np.set_printoptions(threshold=2400)
            print(f"\n{old[3:5]}\n")
            new[3, 0] = 0.99  # Arranges for consistent {old, new} column spacing
            print(new[3:13])
        self.assertEqual(13.0, round(sum(new[3, :])))
        self.assertEqual(10.0, sum(new[10, :]))
        self.assertEqual(7.0, sum(new[11, :]))
        self.assertEqual(0.0, sum(new[12, :]))
