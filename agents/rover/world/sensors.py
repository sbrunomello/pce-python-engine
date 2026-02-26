from __future__ import annotations

from dataclasses import dataclass

Coord = tuple[int, int]


@dataclass(frozen=True)
class SensorReading:
    front: int
    front_left: int
    front_right: int
    left: int
    right: int


DIR_TO_VEC: dict[int, Coord] = {
    0: (0, -1),
    1: (1, 0),
    2: (0, 1),
    3: (-1, 0),
}


def _rotate_left(direction: int) -> int:
    return (direction - 1) % 4


def _rotate_right(direction: int) -> int:
    return (direction + 1) % 4


def distance_to_block(
    origin: Coord,
    direction: int,
    width: int,
    height: int,
    obstacles: set[Coord],
    max_range: int = 10,
) -> int:
    """Return free tiles count until a collision with wall/obstacle."""
    dx, dy = DIR_TO_VEC[direction]
    x, y = origin
    for distance in range(1, max_range + 1):
        nx, ny = x + dx * distance, y + dy * distance
        if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in obstacles:
            return distance - 1
    return max_range


def read_sensors(
    origin: Coord,
    direction: int,
    width: int,
    height: int,
    obstacles: set[Coord],
) -> SensorReading:
    return SensorReading(
        front=distance_to_block(origin, direction, width, height, obstacles),
        front_left=distance_to_block(origin, _rotate_left(direction), width, height, obstacles),
        front_right=distance_to_block(origin, _rotate_right(direction), width, height, obstacles),
        left=distance_to_block(origin, _rotate_left(direction), width, height, obstacles),
        right=distance_to_block(origin, _rotate_right(direction), width, height, obstacles),
    )
