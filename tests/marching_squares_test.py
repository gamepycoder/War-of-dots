# Copyright 2026 John Hanley. MIT licensed.

import unittest
from typing import Any

import numpy as np

from constants import CELL_SIZE, WORLD_X, WORLD_Y
from wod_server import City, Environment, MarchingSquares, Player, dir_dis_to_xy, xy_to_dir_dis

albany = City((3 * CELL_SIZE, 4 * CELL_SIZE))
boston = City((5 * CELL_SIZE, 6 * CELL_SIZE))


def xy_is_within(
    thresh_distance: float,
    xy: tuple[float, float],
) -> tuple[bool, float, float]:
    """In the common case, returns 'not within threshold' with no sqrt() calls."""

    # if manhattan_distance(xy) >= thresh_distance:
    if abs(xy[0]) + abs(xy[1]) >= thresh_distance:
        return False, 0.0, float("inf")
    direc, dist = xy_to_dir_dis(xy)
    return dist < thresh_distance, direc, dist


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


class DeterministicEnvironment2(DeterministicEnvironment):
    def update_troops(self, paths_to_apply: list[tuple[Any, Any]]) -> None:
        self.players_in_cities: list[list[Player]] = [[] for _ in self.cities]
        troop_ids = [info[0] for info in paths_to_apply]
        troop_paths = [info[1] for info in paths_to_apply]
        for player in self.players:
            player.vision.grid = [row[:] for row in self.default_vision]
            for city in self.cities:
                if city.owner is player:
                    self.city_vision_brush.apply(player.vision, city.position, 0)
                    self.city_border_brush.apply(player.border, city.position, 1.0)
            for other_player in self.players:
                if player is not other_player:
                    for city in self.cities:
                        if city.owner is other_player:
                            self.city_border_brush.apply(player.border, city.position, 0.0)
            to_remove = []
            for troop in player.troops:
                if troop.health <= 0:
                    to_remove.append(troop)
                    continue
                try:
                    tidx = troop_ids.index(id(troop))
                    troop.path = troop_paths[tidx]
                except ValueError:
                    pass

                old_pos = troop.position
                owned = [city.position for city in self.cities if city.owner is player]
                if owned:
                    closest_city = min(
                        owned,
                        key=lambda x: xy_to_dir_dis(((old_pos[0] - x[0]), (old_pos[1] - x[1])))[1],
                    )
                    city_dir, city_dist = xy_to_dir_dis(
                        ((old_pos[0] - closest_city[0]), (old_pos[1] - closest_city[1]))
                    )
                    sample_points = [
                        dir_dis_to_xy(city_dir, dist * 20) for dist in range(int(city_dist // 20))
                    ]
                    border_avg = 0
                    if sample_points:
                        border_avgs = []
                        for other_player in self.players:
                            if other_player is not player:
                                border_avgs.append(
                                    sum(
                                        [
                                            other_player.border.get_grid_value(
                                                (closest_city[0] + s_p[0]) / CELL_SIZE,
                                                (closest_city[1] + s_p[1]) / CELL_SIZE,
                                            )
                                            for s_p in sample_points
                                        ]
                                    )
                                    / len(sample_points)
                                )
                        border_avg = int(sum(border_avgs) / len(border_avgs))
                    dist_penal = max(((city_dist + 250) / 1000), 0.5)
                    healing_power = (1 - (border_avg / 2)) - dist_penal
                else:
                    healing_power = -0.5
                troop.health += int(healing_power / 25)
                if troop.health > 100:
                    troop.health = 100

                enemies_in_range = []

                gx = old_pos[0] / CELL_SIZE
                gy = old_pos[1] / CELL_SIZE

                terrain = self.terrain_marching.get_grid_value(gx, gy)
                forest = self.forest_marching.get_grid_value(gx, gy)
                on_terrain = self.get_terrain_name(terrain, forest)

                if troop.path:
                    target = troop.path[0]

                    terrain_speed = self.terrain_speeds[on_terrain]
                    dir, distance = xy_to_dir_dis(
                        (
                            target[0] - old_pos[0],
                            target[1] - old_pos[1],
                        )
                    )
                    distance = terrain_speed * 0.1
                    new_off_x, new_off_y = dir_dis_to_xy(dir, distance)

                    new_pos = (
                        old_pos[0] + new_off_x,
                        old_pos[1] + new_off_y,
                    )

                    for other_t in player.troops:
                        if other_t == troop:
                            continue
                        other_x, other_y = other_t.position
                        old_off_x, old_off_y = (
                            new_pos[0] - other_x,
                            new_pos[1] - other_y,
                        )
                        is_within, dir, distance = xy_is_within(14, (old_off_x, old_off_y))
                        if is_within:
                            distance = 14
                            new_off_x, new_off_y = dir_dis_to_xy(dir, distance)
                            change_x, change_y = (
                                new_off_x - old_off_x,
                                new_off_y - old_off_y,
                            )
                            new_pos = (new_pos[0] + change_x, new_pos[1] + change_y)

                    gx = new_pos[0] / CELL_SIZE
                    gy = new_pos[1] / CELL_SIZE
                    terrain = self.terrain_marching.get_grid_value(gx, gy)
                    forest = self.forest_marching.get_grid_value(gx, gy)
                    new_terrain = self.get_terrain_name(terrain, forest)

                    hit_enemy = False

                    for other_player in self.players:
                        if player is not other_player:
                            self.border_brush.apply(other_player.border, troop.position, 0.0)
                            for other_t in other_player.troops:
                                other_x, other_y = other_t.position
                                off_x, off_y = (
                                    new_pos[0] - other_x,
                                    new_pos[1] - other_y,
                                )
                                is_within, dir, distance = xy_is_within(32, (off_x, off_y))
                                if is_within:
                                    if distance < 28:
                                        hit_enemy = True
                                    if distance < 32:
                                        enemies_in_range.append((other_t, distance))

                    out_of_world = (
                        (new_pos[0] > WORLD_X)
                        or (new_pos[0] < 0)
                        or (new_pos[1] > WORLD_Y)
                        or (new_pos[1] < 0)
                    )
                    if (not new_terrain == "mountain") and not hit_enemy and not out_of_world:
                        troop.position = new_pos
                        on_terrain = new_terrain

                    is_within, dir, distance = xy_is_within(
                        terrain_speed * 2,
                        (target[0] - troop.position[0], target[1] - troop.position[1]),
                    )
                    if is_within and distance < terrain_speed * 2:
                        troop.path.pop(0)
                else:
                    new_pos = old_pos

                    for other_t in player.troops:
                        if other_t == troop:
                            continue
                        other_x, other_y = other_t.position
                        old_off_x, old_off_y = (
                            new_pos[0] - other_x,
                            new_pos[1] - other_y,
                        )
                        is_within, dir, distance = xy_is_within(15, (old_off_x, old_off_y))
                        if is_within:
                            distance += 0.025
                            new_off_x, new_off_y = dir_dis_to_xy(dir, distance)
                            change_x, change_y = (
                                new_off_x - old_off_x,
                                new_off_y - old_off_y,
                            )
                            new_pos = (new_pos[0] + change_x, new_pos[1] + change_y)

                    gx = new_pos[0] / CELL_SIZE
                    gy = new_pos[1] / CELL_SIZE
                    terrain = self.terrain_marching.get_grid_value(gx, gy)
                    forest = self.forest_marching.get_grid_value(gx, gy)
                    new_terrain = self.get_terrain_name(terrain, forest)

                    hit_enemy = False

                    for other_player in self.players:
                        if player is not other_player:
                            self.border_brush.apply(other_player.border, troop.position, 0.0)
                            for other_t in other_player.troops:
                                other_x, other_y = other_t.position
                                off_x, off_y = (
                                    new_pos[0] - other_x,
                                    new_pos[1] - other_y,
                                )
                                is_within, dir, distance = xy_is_within(32, (off_x, off_y))
                                if is_within:
                                    if distance < 28:
                                        hit_enemy = True
                                    if distance < 32:
                                        enemies_in_range.append((other_t, distance))

                    out_of_world = (
                        (new_pos[0] > WORLD_X)
                        or (new_pos[0] < 0)
                        or (new_pos[1] > WORLD_Y)
                        or (new_pos[1] < 0)
                    )
                    if (not new_terrain == "mountain") and not hit_enemy and not out_of_world:
                        troop.position = new_pos
                        on_terrain = new_terrain

                if enemies_in_range:
                    attack_power = int(self.terrain_attacks[on_terrain] / 25)
                    closest = min(enemies_in_range, key=lambda x: x[1])
                    closest[0].health -= attack_power

                if on_terrain == "hill":
                    self.city_vision_brush.apply(player.vision, troop.position, 0)
                else:
                    self.vision_brush.apply(player.vision, troop.position, 0)
                self.border_brush.apply(player.border, troop.position, 1.0)
                for i, city in enumerate(self.cities):
                    cx, cy = city.position
                    tx, ty = troop.position
                    is_within, dir, dist = xy_is_within(15, (tx - cx, ty - cy))
                    if is_within:
                        self.players_in_cities[i].append(player)
                        break
            to_remove.reverse()
            for t in to_remove:
                player.troops.remove(t)


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
        di = env.draw_info(player_num=0)  # vision_grid, border_grid, troops, cities
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
