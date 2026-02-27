#! /usr/bin/env python

import json
from typing import Any

import pygame
import typer

import simple_socket
from constants import (
    CELL_SIZE,
    COLORS,
    COLS,
    PORTS,
    ROWS,
    TABLE,
    TERRAIN_VALUES,
    THRESHOLD,
    WORLD_X,
    WORLD_Y,
)


def interp(threshold, a, b):
    if a == b:
        return 0.5
    t = (threshold - a) / (b - a)
    return max(0.0, min(1.0, t))


def marching_squares(grid, cell_size, rows, cols, threshold):
    segments = []
    cs = cell_size
    for j in range(rows):
        for i in range(cols):
            c0 = grid[j][i]
            c3 = grid[j][i + 1]
            c2 = grid[j + 1][i + 1]
            c1 = grid[j + 1][i]

            p_top = interp(threshold, c0, c1)
            p_right = interp(threshold, c1, c2)
            p_bottom = interp(threshold, c3, c2)
            p_left = interp(threshold, c0, c3)

            x = j * cs
            y = i * cs
            p0 = (x + p_top * cs, y)
            p1 = (x + cs, y + p_right * cs)
            p2 = (x + p_bottom * cs, y + cs)
            p3 = (x, y + p_left * cs)
            idx = 0
            if c0 > threshold:
                idx |= 1
            if c1 > threshold:
                idx |= 2
            if c2 > threshold:
                idx |= 4
            if c3 > threshold:
                idx |= 8
            if idx == 0 or idx == 15:
                pass
            elif idx == 1:
                segments.append((p3, p0))
            elif idx == 2:
                segments.append((p0, p1))
            elif idx == 3:
                segments.append((p3, p1))
            elif idx == 4:
                segments.append((p1, p2))
            elif idx == 5:
                segments.append((p3, p0))
                segments.append((p1, p2))
            elif idx == 6:
                segments.append((p0, p2))
            elif idx == 7:
                segments.append((p3, p2))
            elif idx == 8:
                segments.append((p2, p3))
            elif idx == 9:
                segments.append((p0, p2))
            elif idx == 10:
                segments.append((p0, p1))
                segments.append((p2, p3))
            elif idx == 11:
                segments.append((p1, p2))
            elif idx == 12:
                segments.append((p1, p3))
            elif idx == 13:
                segments.append((p0, p1))
            elif idx == 14:
                segments.append((p3, p0))
    return segments


def marching_squares_poly(grid, cell_size, rows, cols, threshold):
    polys = []
    cs = cell_size
    thr = threshold

    for i in range(rows):
        for j in range(cols):
            c0 = grid[i][j]
            c1 = grid[i][j + 1]
            c2 = grid[i + 1][j + 1]
            c3 = grid[i + 1][j]

            row_pos = i * cs
            col_pos = j * cs

            v0 = (row_pos, col_pos)
            v1 = (row_pos, col_pos + cs)
            v2 = (row_pos + cs, col_pos + cs)
            v3 = (row_pos + cs, col_pos)

            p_top = (row_pos, col_pos + interp(threshold, c0, c1) * cs)
            p_right = (row_pos + interp(threshold, c1, c2) * cs, col_pos + cs)
            p_bottom = (row_pos + cs, col_pos + interp(threshold, c3, c2) * cs)
            p_left = (row_pos + interp(threshold, c0, c3) * cs, col_pos)

            inside = [c0 > thr, c1 > thr, c2 > thr, c3 > thr]
            idx = 0
            if inside[0]:
                idx |= 1
            if inside[1]:
                idx |= 2
            if inside[2]:
                idx |= 4
            if inside[3]:
                idx |= 8

            if idx == 0:
                continue
            if idx == 15:
                polys.append([v0, v1, v2, v3])
                continue

            pts = {
                "v0": v0,
                "v1": v1,
                "v2": v2,
                "v3": v3,
                "p_top": p_top,
                "p_right": p_right,
                "p_bottom": p_bottom,
                "p_left": p_left,
            }

            specs = TABLE.get(idx, [])
            for spec in specs:
                poly = [pts[name] for name in spec]
                compact = []
                for p in poly:
                    if not compact or (
                        abs(p[0] - compact[-1][0]) > 1e-9 or abs(p[1] - compact[-1][1]) > 1e-9
                    ):
                        compact.append(p)
                if len(compact) >= 3:
                    polys.append(compact)

    return polys


def marching_squares_layers(grid, cell_size, rows, cols, thresholds):
    layers = []
    for thr in thresholds:
        threshold = thr
        polys = marching_squares_poly(grid, cell_size, rows, cols, threshold)
        layers.append(polys)
    return layers


class Game:
    def __init__(self, title):
        pygame.init()
        info_object = pygame.display.Info()
        desktop_width = info_object.current_w
        desktop_height = info_object.current_h
        self.size = (desktop_width - 20, desktop_height - 100)
        self.factor = min(self.size[0] / WORLD_X, self.size[1] / WORLD_Y)
        self.screen = pygame.display.set_mode(self.size)
        pygame.display.set_caption(title)
        pygame.event.set_allowed(
            [
                pygame.KEYDOWN,
                pygame.QUIT,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION,
                pygame.MOUSEWHEEL,
            ]
        )
        self.clock = pygame.time.Clock()
        self.done = False

        self.zoom_levels = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3.5, 4, 6]
        self.zoom_idx = self.zoom_levels.index(1)
        self.zoom = self.get_zoom(self.zoom_idx)

        self.camx, self.camy = 0.0, 0.0

        self.panning = False
        self.pan_start_mouse = (0, 0)
        self.pan_start_cam = (0.0, 0.0)

        self.draw_info: list[Any] = []
        self.player_input: str | list[list[int]] = [[], []]  # There is room to improve this.
        self.paths = []
        self.drawing_path = False
        self.city_paths = []
        self.drawing_city_path = False

        self.pause = False

        self.terrain_by_zoom = {}

    def run_game(self, ip: str, port: int):
        print("connecting...")
        self.client = simple_socket.Client(ip, PORTS[min(99, max(0, int(port)))])
        self.client.connect()
        print("connection successful!")

        print("drawing terrain...")
        terrain_grid, forrest_grid, cities, self.player_num = json.loads(self.client.rcv())
        self.color = COLORS[self.player_num]
        layers = marching_squares_layers(
            terrain_grid, CELL_SIZE, ROWS, COLS, list(TERRAIN_VALUES.values())
        )
        layers.append(marching_squares_poly(forrest_grid, CELL_SIZE, ROWS, COLS, THRESHOLD))

        for i in range(len(self.zoom_levels)):
            z = self.get_zoom(i)
            sw = max(1, int(WORLD_X * z))
            sh = max(1, int(WORLD_Y * z))
            surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
            for poly in layers[0]:
                scaled = [(int(x * z), int(y * z)) for x, y in poly]
                pygame.draw.polygon(surf, (0, 220, 255), scaled, 0)
            for poly in layers[1]:
                scaled = [(int(x * z), int(y * z)) for x, y in poly]
                pygame.draw.polygon(surf, (20, 180, 20), scaled, 0)
            for poly in layers[2]:
                scaled = [(int(x * z), int(y * z)) for x, y in poly]
                pygame.draw.polygon(surf, (150, 150, 150), scaled, 0)
            for poly in layers[3]:
                scaled = [(int(x * z), int(y * z)) for x, y in poly]
                pygame.draw.polygon(surf, (100, 100, 100), scaled, 0)
            for poly in layers[4]:
                scaled = [(int(x * z), int(y * z)) for x, y in poly]
                pygame.draw.polygon(surf, (30, 125, 30), scaled, 0)

            for position in cities:
                if position is None:
                    continue
                cx, cy = int(position[0] * z), int(position[1] * z)
                pygame.draw.circle(surf, (255, 215, 0), (cx, cy), max(1, int(15 * z)))
            self.terrain_by_zoom[z] = surf

        print("terrain drawn! starting game (waiting for other players)...")
        self.draw_info = json.loads(self.client.rcv())
        while not self.done:
            self.handle_events()
            self.draw()
            pygame.display.flip()
            self.clock.tick(30)
        self.client.close()
        pygame.quit()

    def handle_events(self):
        if not self.pause:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.done = True
                    self.player_input = "close"

                elif e.type == pygame.MOUSEBUTTONDOWN:
                    if e.button == 3 and not self.drawing_path and not self.drawing_city_path:
                        self.panning = True
                        self.pan_start_mouse = e.pos
                        self.pan_start_cam = (self.camx, self.camy)

                    elif e.button == 4 and not self.drawing_path and not self.drawing_city_path:
                        self.zoom_in_at(e.pos)
                    elif e.button == 5 and not self.drawing_path and not self.drawing_city_path:
                        self.zoom_out_at(e.pos)

                    elif e.button == 1:
                        mx, my = e.pos[0], e.pos[1]
                        troops = self.draw_info[2]

                        r = max(1, int(7 * self.zoom))
                        r3 = r * 3
                        best = None
                        best_dist2 = None
                        best_pos = None
                        for pos, color, tid, owner, path, health in troops:
                            if owner == self.player_num:
                                sx = int((pos[0] - self.camx) * self.zoom)
                                sy = int((pos[1] - self.camy) * self.zoom)
                                dx = (mx) - sx
                                dy = (my) - sy
                                d2 = dx * dx + dy * dy
                                if d2 <= r3 * r3:
                                    if best is None or d2 < best_dist2:
                                        best_pos = pos
                                        best = tid
                                        best_dist2 = d2

                        if best is not None:
                            self.drawing_path = True

                            wx = self.camx + mx / self.zoom
                            wy = self.camy + my / self.zoom
                            to_pop = None
                            for i, id_path in enumerate(self.paths):
                                if id_path[0] == best:
                                    to_pop = i
                            if to_pop is not None:
                                self.paths.pop(to_pop)
                            self.paths.append((best, [best_pos]))

                        else:
                            mx, my = e.pos[0], e.pos[1]
                            cities = self.draw_info[3]

                            r = max(1, int(7 * self.zoom))
                            r3 = r * 3
                            best_city = None
                            best_dist2 = None
                            best_pos = None
                            for color, pos, cid, path, owner in cities:
                                if owner == self.player_num:
                                    sx = int((pos[0] - self.camx) * self.zoom)
                                    sy = int((pos[1] - self.camy) * self.zoom)
                                    dx = (mx) - sx
                                    dy = (my) - sy
                                    d2 = dx * dx + dy * dy
                                    if d2 <= r3 * r3:
                                        if best_city is None or d2 < best_dist2:
                                            best_pos = pos
                                            best_city = cid
                                            best_dist2 = d2

                            if best_city is not None:
                                self.drawing_city_path = True

                                wx = self.camx + mx / self.zoom
                                wy = self.camy + my / self.zoom
                                to_pop = None
                                for i, id_path in enumerate(self.city_paths):
                                    if id_path[0] == best_city:
                                        to_pop = i
                                if to_pop is not None:
                                    self.city_paths.pop(to_pop)
                                self.city_paths.append((best_city, [best_pos]))

                elif e.type == pygame.MOUSEBUTTONUP:
                    if e.button == 3:
                        self.panning = False
                    if e.button == 1:
                        self.drawing_path = False
                        self.drawing_city_path = False

                elif e.type == pygame.MOUSEMOTION:
                    if self.drawing_path:
                        mx, my = e.pos
                        wx = self.camx + (mx) / self.zoom
                        wy = self.camy + (my) / self.zoom
                        lx, ly = self.paths[-1][1][-1]
                        dx = wx - lx
                        dy = wy - ly
                        if dx * dx + dy * dy > (14.0 / max(1.0, self.zoom)):
                            self.paths[-1][1].append((wx, wy))
                    elif self.drawing_city_path:
                        mx, my = e.pos
                        wx = self.camx + (mx) / self.zoom
                        wy = self.camy + (my) / self.zoom
                        lx, ly = self.city_paths[-1][1][-1]
                        dx = wx - lx
                        dy = wy - ly
                        if dx * dx + dy * dy > (14.0 / max(1.0, self.zoom)):
                            self.city_paths[-1][1].append((wx, wy))
                    elif self.panning:
                        mx, my = e.pos
                        sx, sy = self.pan_start_mouse
                        dx = (mx) - sx
                        dy = (my) - sy

                        self.camx = self.pan_start_cam[0] - dx / self.zoom
                        self.camy = self.pan_start_cam[1] - dy / self.zoom
                        self.clamp_camera()

                elif e.type == pygame.MOUSEWHEEL:
                    if not self.drawing_path and not self.drawing_city_path:
                        mx, my = pygame.mouse.get_pos()
                        if e.y > 0:
                            self.zoom_in_at((mx, my))
                        elif e.y < 0:
                            self.zoom_out_at((mx, my))

                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_c:
                        self.paths = []
                        self.city_paths = []

                    elif e.key == pygame.K_SPACE:
                        if (not self.drawing_path and not self.drawing_city_path) and (
                            self.paths or self.city_paths
                        ):
                            for id, path in self.paths:
                                path.pop(0)
                            for id, path in self.city_paths:
                                path.pop(0)
                            assert isinstance(self.player_input, list)
                            self.player_input[0] = self.paths
                            self.player_input[1] = self.city_paths
                            self.paths = []
                            self.city_paths = []
                    elif e.key == pygame.K_p:
                        self.player_input = "pause"
                        self.pause = True
        else:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.done = True
                    self.player_input = "close"
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_p:
                        self.player_input = "unpause"
                        self.pause = False

        self.client.send(json.dumps(self.player_input, separators=(",", ":")))
        self.player_input = [[], []]

    def zoom_in_at(self, screen_pos):
        if self.zoom_idx < len(self.zoom_levels) - 1:
            self.set_zoom_index(self.zoom_idx + 1, screen_pos)

    def zoom_out_at(self, screen_pos):
        if self.zoom_idx > 0:
            self.set_zoom_index(self.zoom_idx - 1, screen_pos)

    def get_zoom(self, zoom_idx):
        return self.zoom_levels[zoom_idx] * self.factor

    def set_zoom_index(self, new_idx, screen_pos):
        old_zoom = self.zoom
        new_zoom = self.get_zoom(new_idx)
        sx, sy = screen_pos

        world_x = self.camx + sx / old_zoom
        world_y = self.camy + sy / old_zoom

        self.zoom_idx = new_idx
        self.zoom = new_zoom
        self.camx = world_x - sx / new_zoom
        self.camy = world_y - sy / new_zoom
        self.clamp_camera()

    def clamp_camera(self):
        max_camx = max(0.0, WORLD_X - (self.size[0] / self.zoom))
        max_camy = max(0.0, WORLD_Y - (self.size[1] / self.zoom))
        if self.camx < 0.0:
            self.camx = 0.0
        if self.camy < 0.0:
            self.camy = 0.0
        if self.camx > max_camx:
            self.camx = max_camx
        if self.camy > max_camy:
            self.camy = max_camy

    def draw(self):
        self.screen.fill((255, 255, 255))
        vision_grid, border_grid, troops, cities = self.draw_info = json.loads(self.client.rcv())

        z = self.zoom

        terrain_surf = self.terrain_by_zoom[z]
        offset_x = int(-self.camx * z)
        offset_y = int(-self.camy * z)
        self.screen.blit(terrain_surf, (offset_x, offset_y))

        dyn_w = max(1, int(WORLD_X * z))
        dyn_h = max(1, int(WORLD_Y * z))
        dynamic = pygame.Surface((dyn_w, dyn_h), pygame.SRCALPHA)
        fog = pygame.Surface((dyn_w, dyn_h), pygame.SRCALPHA)

        paths_to_draw = []
        for color, position, cid, path, owner in cities:
            if path and owner == self.player_num:
                path.insert(0, position)
                paths_to_draw.append(path)
            if color is not None:
                px = int(position[0] * z)
                py = int(position[1] * z)

                pole_bottom = (px, py)
                pole_top = (px, int(py - 30 * z))
                pygame.draw.line(dynamic, (80, 80, 80), pole_bottom, pole_top, max(1, int(3 * z)))

                flag_color = tuple(color) if isinstance(color, (list, tuple)) else color
                fw, fh = int(20 * z), int(14 * z)
                p1 = (pole_top[0], pole_top[1])
                p2 = (pole_top[0] + fw, pole_top[1] + fh // 2)
                p3 = (pole_top[0], pole_top[1] + fh)
                pygame.draw.polygon(dynamic, flag_color, [p1, p2, p3])
                pygame.draw.polygon(dynamic, (0, 0, 0), [p1, p2, p3], max(1, int(1 * z)))

        for path in paths_to_draw:
            for i, pos in enumerate(path):
                if not i == (len(path) - 1):
                    px = int(pos[0] * z)
                    py = int(pos[1] * z)
                    px2 = int(path[i + 1][0] * z)
                    py2 = int(path[i + 1][1] * z)
                    pygame.draw.line(
                        dynamic, (240, 180, 0), (px, py), (px2, py2), max(1, int(4 * z))
                    )

        paths_to_draw = []
        tids = [tid for tid, path in self.paths]
        for pos, color, tid, owner, path, health in troops:
            px = int(pos[0] * z)
            py = int(pos[1] * z)
            r = max(1, int(7 * z))
            rgb = color

            if tid in tids:
                factor = 0.5
                rgb = [max(0, min(255, int(x * factor))) for x in color]
            if path and owner == self.player_num:
                path.insert(0, pos)
                paths_to_draw.append(path)
            pygame.draw.rect(
                dynamic,
                (0, 255, 0),
                pygame.rect.Rect(
                    px - r,
                    (py - r) - max(1, int(3 * z)),
                    (r * 2) * (health / 100),
                    max(1, int(3 * z)),
                ),
            )
            pygame.draw.circle(dynamic, rgb, (px, py), r)

        for path in paths_to_draw:
            for i, pos in enumerate(path):
                if not i == (len(path) - 1):
                    px = int(pos[0] * z)
                    py = int(pos[1] * z)
                    px2 = int(path[i + 1][0] * z)
                    py2 = int(path[i + 1][1] * z)
                    pygame.draw.line(dynamic, self.color, (px, py), (px2, py2), max(1, int(2 * z)))

        for tid, path in self.paths:
            for i, pos in enumerate(path):
                if not i == (len(path) - 1):
                    px = int(pos[0] * z)
                    py = int(pos[1] * z)
                    px2 = int(path[i + 1][0] * z)
                    py2 = int(path[i + 1][1] * z)
                    pygame.draw.line(dynamic, (0, 0, 0), (px, py), (px2, py2), max(1, int(2 * z)))
        for tid, path in self.city_paths:
            for i, pos in enumerate(path):
                if not i == (len(path) - 1):
                    px = int(pos[0] * z)
                    py = int(pos[1] * z)
                    px2 = int(path[i + 1][0] * z)
                    py2 = int(path[i + 1][1] * z)
                    pygame.draw.line(dynamic, (0, 0, 0), (px, py), (px2, py2), max(1, int(2 * z)))

        for a, b in marching_squares(border_grid, CELL_SIZE, ROWS, COLS, THRESHOLD):
            ax = int(a[0] * z)
            ay = int(a[1] * z)
            bx = int(b[0] * z)
            by = int(b[1] * z)
            pygame.draw.line(fog, (0, 0, 0), (ax, ay), (bx, by), max(1, int(3 * z)))

        for poly in marching_squares_poly(vision_grid, CELL_SIZE, ROWS, COLS, THRESHOLD):
            scaled = [(int(x * z), int(y * z)) for x, y in poly]
            pygame.draw.polygon(fog, (0, 0, 0, 150), scaled, 0)

        if self.pause:
            font = pygame.font.SysFont(None, 48)

            text_surface = font.render("Pause", False, (0, 0, 0))

            fog.blit(text_surface, (10, 10))

        self.screen.blit(dynamic, (offset_x, offset_y))
        self.screen.blit(fog, (offset_x, offset_y))


def main(ip: str = "", port: int = 0) -> None:
    game_play = Game("WAR OF DOTS")
    game_play.run_game(ip, port)


if __name__ == "__main__":
    typer.run(main)
