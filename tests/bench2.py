#! /usr/bin/env python

from time import time

from constants import CELL_SIZE, WORLD_X, WORLD_Y
from tests.bench import BenchmarkGame, add_troops
from tests.marching_squares_test import DeterministicEnvironment
from wod_server import dir_dis_to_xy, xy_to_dir_dis


class DeterministicEnvironment2(DeterministicEnvironment):
    def update_troops(self, paths_to_apply):  # split into more functions ?
        self.players_in_cities = [[] for _ in self.cities]
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
                        border_avg = sum(border_avgs) / len(border_avgs)
                    dist_penal = max(((city_dist + 250) / 1000), 0.5)
                    healing_power = (1 - (border_avg / 2)) - dist_penal
                else:
                    healing_power = -0.5
                troop.health += healing_power / 25
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
                        dir, distance = xy_to_dir_dis((old_off_x, old_off_y))
                        if distance < 14:
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
                                dir, distance = xy_to_dir_dis((off_x, off_y))
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

                    dir, distance = xy_to_dir_dis(
                        (target[0] - troop.position[0], target[1] - troop.position[1])
                    )
                    if distance < (terrain_speed * 2):
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
                        dir, distance = xy_to_dir_dis((old_off_x, old_off_y))
                        if distance < 15:
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
                                dir, distance = xy_to_dir_dis((off_x, off_y))
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
                    attack_power = self.terrain_attacks[on_terrain] / 25
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
                    dir, dist = xy_to_dir_dis((tx - cx, ty - cy))
                    if dist < 15:
                        self.players_in_cities[i].append(player)
                        break
            to_remove.reverse()
            for t in to_remove:
                player.troops.remove(t)


def bench2(num_update_cycles: int = 1_000) -> None:
    game = BenchmarkGame()
    game.environment = add_troops(DeterministicEnvironment2())

    t0 = time()
    for _ in range(num_update_cycles):
        game.game_logic()
    elapsed = round(time() - t0, 3)
    print(f"{elapsed=} seconds")


if __name__ == "__main__":
    bench2()
