#! /usr/bin/env python

# Copyright 2026 John Hanley. MIT licensed.

from time import time

from tests.bench import BenchmarkGame, add_troops
from tests.marching_squares_test import DeterministicEnvironment2


def manhattan_distance(position: tuple[float, float]) -> float:
    """Taxicab distance between a NYC street address and the (0, 0) origin.
    It avoids expensive sqrt() calls."""
    x, y = position
    return abs(x) + abs(y)


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
