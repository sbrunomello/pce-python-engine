from __future__ import annotations

import random
from collections.abc import Iterable

Coord = tuple[int, int]


def generate_obstacles(width: int, height: int, seed: int, density: float = 0.12) -> set[Coord]:
    """Generate deterministic obstacle coordinates using a seeded RNG."""
    rng = random.Random(seed)
    target = int(width * height * density)
    obstacles: set[Coord] = set()
    while len(obstacles) < target:
        x = rng.randrange(0, width)
        y = rng.randrange(0, height)
        obstacles.add((x, y))
    return obstacles


def random_free_cell(width: int, height: int, obstacles: Iterable[Coord], seed: int) -> Coord:
    """Pick a deterministic free cell."""
    blocked = set(obstacles)
    rng = random.Random(seed)
    while True:
        candidate = (rng.randrange(0, width), rng.randrange(0, height))
        if candidate not in blocked:
            return candidate
