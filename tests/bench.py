#! /usr/bin/env python

from time import time

from constants import PLAYERS
from tests.marching_squares_test import DeterministicEnvironment
from wod_server import Environment, Game, Troop


class BenchmarkGame(Game):
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
        assert len(paths_to_apply) == 0
        self.environment.update_troops(paths_to_apply)
        self.ready = True


def add_troops(env: Environment, num_troops: int = 40) -> Environment:
    for i, city in enumerate(env.cities):  # We assume 2 cities and 2 players.
        x, y = city.position
        assert 4 == len(env.draw_info(player=i))
        player = env.players[i]
        for _ in range(num_troops):
            player.troops.append(Troop((x + 2 * i, y + i), player))

    return env


def bench(num_update_cycles: int = 1_000) -> None:
    game = BenchmarkGame()
    game.environment = add_troops(DeterministicEnvironment())

    t0 = time()
    for _ in range(num_update_cycles):
        game.game_logic()
    elapsed = round(time() - t0, 3)
    print(f"{elapsed=} seconds")


if __name__ == "__main__":
    bench()
