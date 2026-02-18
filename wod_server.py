import json
import math
import random
import socket
import threading
import time

import perlin_noise

import simple_socket
from constants import (
    CELL_SIZE,
    COLORS,
    COLS,
    PLAYERS,
    PORTS,
    ROWS,
    TERRAIN_VALUES,
    THRESHOLD,
    WORLD_X,
    WORLD_Y,
)


def dir_dis_to_xy(direction, distance):
    return (
        (distance * math.cos(math.radians(direction))),
        (distance * math.sin(math.radians(direction))),
    )


def xy_to_dir_dis(xy):
    x, y = xy
    return (
        math.degrees(math.atan2(y, x)),
        math.sqrt(x**2 + y**2),
    )


class MarchingSquares:
    def __init__(self):
        self.grid = [[0.0 for _ in range(COLS + 1)] for _ in range(ROWS + 1)]

    def set_grid(self, new_grid):
        self.grid = new_grid

    def get_grid_value(self, x: float, y: float) -> float:
        x1, y1 = int(x), int(y)
        x2, y2 = min(x1 + 1, ROWS), min(y1 + 1, COLS)

        dx, dy = x - x1, y - y1

        p11 = self.grid[x1][y1]
        p21 = self.grid[x2][y1]
        p12 = self.grid[x1][y2]
        p22 = self.grid[x2][y2]

        #fmt: off
        return (
            p11 * (1 - dx) * (1 - dy)
            + p21 * dx * (1 - dy)
            + p12 * (1 - dx) * dy
            + p22 * dx * dy
        )
        #fmt: on


class Brush:
    def __init__(self, radius=40, strength=1.0, falloff=1.0):
        self.radius = radius
        self.strength = strength
        self.falloff = falloff

    def apply(self, marching_squares, pos, target_value):
        mx, my = pos
        cs = CELL_SIZE
        r = float(self.radius)
        if r <= 0:
            return

        col_start = max(0, int((my - r) / cs))
        col_end = min(COLS, int((my + r) / cs) + 1)
        row_start = max(0, int((mx - r) / cs))
        row_end = min(ROWS, int((mx + r) / cs) + 1)

        inv_r = 1.0 / r
        grid = marching_squares.grid
        strength = self.strength
        falloff = self.falloff

        for j in range(row_start, row_end):
            px = j * cs
            dx_sq = (px - mx) ** 2
            row = grid[j]

            for i in range(col_start, col_end):
                py = i * cs
                dy = py - my
                dist_sq = dy * dy + dx_sq

                if dist_sq <= r * r:
                    dist = math.sqrt(dist_sq)
                    t = dist * inv_r

                    weight = strength + t * (falloff - strength)

                    old = row[i]
                    row[i] = max(0.0, min(1.0, old + (target_value - old) * weight))


class Environment:
    def __init__(self):
        self.terrain_speeds = {
            "water": 0.6,
            "forest": 0.8,
            "plains": 1,
            "hill": 0.7,
            "mountain": 3,
        }
        self.terrain_attacks = {
            "water": 0.5,
            "forest": 0.75,
            "plains": 1,
            "hill": 1.5,
            "mountain": 0,
        }
        self.terrain_marching = MarchingSquares()
        self.forest_marching = MarchingSquares()

        self.cities = []

        self.default_vision = [[0.0 for _ in range(COLS + 1)] for _ in range(ROWS + 1)]
        for y in range(COLS + 1):
            for x in range(ROWS + 1):
                self.default_vision[x][y] = 0.0

        self.generate_terrain()
        self.generate_default_vision()
        # 2 players left and right most cities
        # 3 players left-bottom, top, right-bottom
        # 4 players left-bottom, top-left, top-right, right-bottom
        # 5 players left-bottom, top-left, middle, top-right, right-bottom
        # 6 players left-bottom, top-left, middle-left, middle-right, top-right, right-bottom
        left_bottom_city = min(self.cities, key=lambda c: c.position[0] + c.position[1])
        top_left_city = min(self.cities, key=lambda c: c.position[0] - c.position[1])
        middle_top_city = min(
            self.cities,
            key=lambda c: (abs(c.position[0] - (ROWS * CELL_SIZE) / 2) * 1.5) + c.position[1],
        )
        middle_bottom_city = max(
            self.cities,
            key=lambda c: c.position[1] - (abs(c.position[0] - (ROWS * CELL_SIZE) / 2) * 1.5),
        )
        top_right_city = max(self.cities, key=lambda c: c.position[0] - c.position[1])
        right_bottom_city = max(self.cities, key=lambda c: c.position[0] + c.position[1])
        left_city = min(self.cities, key=lambda c: c.position[0])
        right_city = max(self.cities, key=lambda c: c.position[0])
        top_city = max(self.cities, key=lambda c: c.position[1])
        middle_city = min(
            self.cities,
            key=lambda c: abs(c.position[0] - (ROWS * CELL_SIZE) / 2)
            + abs(c.position[1] - (COLS * CELL_SIZE) / 2),
        )
        if PLAYERS == 2:
            self.players = [
                Player(left_city.position, COLORS[0], self),
                Player(right_city.position, COLORS[1], self),
            ]
            left_city.owner = self.players[0]
            right_city.owner = self.players[1]
        elif PLAYERS == 3:
            self.players = [
                Player(left_bottom_city.position, COLORS[0], self),
                Player(right_bottom_city.position, COLORS[1], self),
                Player(top_city.position, COLORS[2], self),
            ]
            left_bottom_city.owner = self.players[0]
            right_bottom_city.owner = self.players[1]
            top_city.owner = self.players[2]
        elif PLAYERS == 4:
            self.players = [
                Player(left_bottom_city.position, COLORS[0], self),
                Player(top_left_city.position, COLORS[1], self),
                Player(top_right_city.position, COLORS[2], self),
                Player(right_bottom_city.position, COLORS[3], self),
            ]
            left_bottom_city.owner = self.players[0]
            top_left_city.owner = self.players[1]
            top_right_city.owner = self.players[2]
            right_bottom_city.owner = self.players[3]
        elif PLAYERS == 5:
            self.players = [
                Player(left_bottom_city.position, COLORS[0], self),
                Player(top_left_city.position, COLORS[1], self),
                Player(middle_city.position, COLORS[2], self),
                Player(top_right_city.position, COLORS[3], self),
                Player(right_bottom_city.position, COLORS[4], self),
            ]
            left_bottom_city.owner = self.players[0]
            top_left_city.owner = self.players[1]
            middle_city.owner = self.players[2]
            top_right_city.owner = self.players[3]
            right_bottom_city.owner = self.players[4]
        elif PLAYERS == 6:
            self.players = [
                Player(left_bottom_city.position, COLORS[0], self),
                Player(top_left_city.position, COLORS[1], self),
                Player(middle_top_city.position, COLORS[2], self),
                Player(middle_bottom_city.position, COLORS[3], self),
                Player(top_right_city.position, COLORS[4], self),
                Player(right_bottom_city.position, COLORS[5], self),
            ]
            left_bottom_city.owner = self.players[0]
            top_left_city.owner = self.players[1]
            middle_top_city.owner = self.players[2]
            middle_bottom_city.owner = self.players[3]
            top_right_city.owner = self.players[4]
            right_bottom_city.owner = self.players[5]
        self.vision_brush = Brush(75, 1, 0)
        self.city_vision_brush = Brush(175, 1, 0)
        self.border_brush = Brush(40, 0.05, 0)
        self.city_border_brush = Brush(80, 0.05, 0)
        self.players_in_cities = [[] for _ in self.cities]

    def generate_terrain(self):
        def elevation_bias(x, y):
            cx = ROWS / 2
            cy = COLS / 2
            dx = abs(x - cx)
            dy = abs(y - cy)
            dist = math.sqrt((dx) ** 2 + (dy) ** 2)
            max_dist = math.sqrt((cx) ** 2 + (cy) ** 2)
            return 1.0 - (dist / max_dist)

        noise = perlin_noise.PerlinNoise(octaves=3)
        for y in range(COLS + 1):
            for x in range(ROWS + 1):
                value = max(
                    0,
                    min(1, ((noise([x / 25, y / 25])) - 0.2) + (elevation_bias(x, y))),
                )
                self.terrain_marching.grid[x][y] = value
        forest_noise = perlin_noise.PerlinNoise(octaves=1.1)
        for y in range(COLS + 1):
            for x in range(ROWS + 1):
                terrain_value = self.terrain_marching.grid[x][y]
                value = (min(0.6, forest_noise([x / 30, y / 30])) * 2.0) + 0.3
                plains_diff = max(0, (TERRAIN_VALUES["plains"] + 0.1) - terrain_value)
                hill_diff = max(0, terrain_value - (TERRAIN_VALUES["hill"] - 0.1))

                self.forest_marching.grid[x][y] = (value - (plains_diff * 10)) - hill_diff * 10

        def within_edges(cx, cy):
            edge_margin = int(1)
            return (
                cx >= edge_margin
                and cx <= ROWS - edge_margin
                and cy >= edge_margin
                and cy <= COLS - edge_margin
            )

        tries = 0
        distance = 15
        while True:
            cx = random.randint(0, ROWS)
            cy = random.randint(0, COLS)
            terrain_value = self.terrain_marching.grid[cx][cy]

            if (
                (
                    terrain_value > TERRAIN_VALUES["plains"]
                    and terrain_value < TERRAIN_VALUES["hill"]
                )
                and all(
                    abs(cx * CELL_SIZE - city.position[0]) + abs(cy * CELL_SIZE - city.position[1])
                    >= CELL_SIZE * distance
                    for city in self.cities
                )
                and within_edges(cx, cy)
                and self.forest_marching.grid[cx][cy] < THRESHOLD
            ):
                px = cx * CELL_SIZE
                py = cy * CELL_SIZE
                self.cities.append(City((px, py)))
                distance = 15
            if len(self.cities) >= 10:
                break
            tries += 1
            if tries >= 100:
                distance = max(2, distance - 2)
                tries = 0

    def generate_default_vision(self):
        for y in range(COLS + 1):
            for x in range(ROWS + 1):
                terrain_value = self.terrain_marching.grid[x][y]
                forest_value = self.forest_marching.grid[x][y]
                self.default_vision[x][y] = 0.35 + (
                    max(min((((terrain_value + 0.1) / 1) + 0.2), 1), 0.2)
                    + (0.8 if forest_value > 0.6 else 0.0)
                )

    def draw_info(self, player):
        ply = self.players[player]
        vision_grid = ply.vision.grid
        border_grid = ply.border.grid
        troops = []
        cities = [
            (
                c.owner.color if c.owner is not None else None,
                c.position,
                c.id,
                c.path,
                self.players.index(c.owner) if c.owner is not None else -1,
            )
            for c in self.cities
        ]
        for troop in [t for p in self.players for t in p.troops]:
            ply = self.players[player]

            vision = ply.vision
            px, py = troop.position
            gx = px / CELL_SIZE
            gy = py / CELL_SIZE
            gx = max(0, min(ROWS, gx))
            gy = max(0, min(COLS, gy))

            if vision.get_grid_value(gx, gy) < THRESHOLD:
                troops.append(
                    (
                        troop.position,
                        troop.owner.color,
                        troop.id,
                        self.players.index(troop.owner),
                        troop.path,
                        troop.health,
                    )
                )

        return vision_grid, border_grid, troops, cities

    def get_terrain_info(self):
        return (
            self.terrain_marching.grid,
            self.forest_marching.grid,
            [c.position for c in self.cities],
        )

    def get_terrain_name(self, value, fvalue):
        if fvalue > THRESHOLD:
            return "forest"
        for name, v in reversed(TERRAIN_VALUES.items()):
            if value > v:
                return name

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

    def update_cities(self, paths_to_apply):
        city_ids = [info[0] for info in paths_to_apply]
        city_paths = [info[1] for info in paths_to_apply]
        for i, city in enumerate(self.cities):
            try:
                cidx = city_ids.index(id(city))
                city.path = city_paths[cidx]
            except ValueError:
                pass
            cx, cy = city.position
            last_owner = city.owner
            if len(self.players_in_cities[i]) == 1:
                city.owner = self.players_in_cities[i][0]
            if last_owner is not city.owner:
                city.timer = 0
                city.path = []
            if city.owner is not None:
                city.timer += 1
                t_per_c = len(city.owner.troops) / len(
                    [c for c in self.cities if c.owner == city.owner]
                )
                if city.timer >= 45 * (30 * t_per_c) and t_per_c < 10:
                    city.owner.troops.append(
                        Troop(
                            (
                                cx + random.randrange(-6, 6),
                                cy + random.randrange(-6, 6),
                            ),
                            city.owner,
                            city.path.copy(),
                        )
                    )
                    city.timer = 0


class Troop:
    def __init__(self, position, owner, path=None):
        self.position = position
        self.health = 100
        self.path = path if path is not None else []
        self.owner = owner
        self.id = id(self)


class City:
    def __init__(self, position):
        self.position = position
        self.timer = 0
        self.owner = None
        self.id = id(self)
        self.path = []


class Player:
    def __init__(self, start_pos, color, environment):
        self.start_pos = start_pos
        self.color = color
        self.troops = [Troop(self.start_pos, self)]
        self.border = MarchingSquares()
        self.vision = MarchingSquares()
        self.vision.grid = [row[:] for row in environment.default_vision]


class Game:
    def __init__(self):
        self.FPS = 45
        self.last_time = time.perf_counter()
        self.frame_time = 1 / self.FPS
        self.done = False
        self.server = simple_socket.Server(socket.gethostbyname(str(socket.gethostname())), 1200)
        self.environment = Environment()
        self.player_inputs = [[] for i in range(PLAYERS)]
        self.player_city_inputs = [[] for i in range(PLAYERS)]
        self.player_pause_requests = [False for i in range(PLAYERS)]
        self.started = False

    def run_game(self):
        self.ready = True
        try:
            port = int(input("Enter port to use (0 - 99): "))
            self.server.port = PORTS[max(0, min(99, port))]
        except ValueError:
            pass
        print("ip: ", self.server.ip, ", port: ", self.server.port)
        print("starting server...")
        self.server.start()
        print("waiting for players...")
        self.server.lsn(conns=PLAYERS)
        for player_num in range(PLAYERS):
            conn, addr = self.server.accept()
            player_thread = threading.Thread(
                target=self.handle_player, args=(player_num, conn, addr)
            )
            player_thread.start()
            print("player: ", player_num, " connected")
        print("All players connected, starting game!")
        self.started = True
        while not self.done:
            if not all(self.player_pause_requests):
                self.game_logic()
            current_time = time.perf_counter()
            delta_time = current_time - self.last_time
            self.last_time = current_time
            if delta_time < self.frame_time:
                time.sleep(self.frame_time - delta_time)
            # elif delta_time < self.frame_time*0.75:
            #     self.dots = len(self.environment.players[0].troops)
            #     print(self.dots)

    def handle_player(self, player_number, conn, addr):
        self.server.send(
            [conn],
            json.dumps(
                (
                    *self.environment.get_terrain_info(),
                    player_number,
                ),
                separators=(",", ":"),
            ),
        )
        while not self.started:
            time.sleep(0.1)
        draw_info = json.dumps([[], [], [], []], separators=(",", ":"))
        while True:
            if self.ready:
                draw_info = json.dumps(
                    self.environment.draw_info(player_number), separators=(",", ":")
                )
                self.server.send([conn], draw_info)
            else:
                self.server.send([conn], draw_info)
            player_in = json.loads(self.server.rcv(conn))
            if player_in == "close" or self.done:
                self.done = True
                self.server.close(conn)
                print("player: ", player_number, " left")
                break
            if player_in:
                if player_in == "pause":
                    self.player_pause_requests[player_number] = True
                elif player_in == "unpause":
                    self.player_pause_requests[player_number] = False
                else:
                    self.player_inputs[player_number].extend(player_in[0])
                    self.player_city_inputs[player_number].extend(player_in[1])

    def game_logic(self):
        city_paths_to_apply = []
        for p_num in range(PLAYERS):
            if self.player_city_inputs[p_num]:
                city_paths_to_apply.extend(self.player_city_inputs[p_num])
        self.player_city_inputs = [[] for i in range(PLAYERS)]
        self.environment.update_cities(city_paths_to_apply)
        paths_to_apply = []
        for p_num in range(PLAYERS):
            if self.player_inputs[p_num]:
                paths_to_apply.extend(self.player_inputs[p_num])
        self.player_inputs = [[] for i in range(PLAYERS)]
        self.ready = False
        self.environment.update_troops(paths_to_apply)
        self.ready = True


def main() -> None:
    game_play = Game()
    game_play.run_game()


if __name__ == "__main__":
    main()
