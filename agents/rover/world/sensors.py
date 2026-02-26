from __future__ import annotations

from dataclasses import dataclass
import random

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


def distance_to_block_vec(
    origin: Coord,
    vec: Coord,
    width: int,
    height: int,
    obstacles: set[Coord],
    max_range: int = 10,
) -> int:
    """Return free tiles count until a collision with wall/obstacle for custom vectors."""
    dx, dy = vec
    x, y = origin
    for distance in range(1, max_range + 1):
        nx, ny = x + dx * distance, y + dy * distance
        if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in obstacles:
            return distance - 1
    return max_range


def _clamp_direction(value: int) -> int:
    return max(-1, min(1, value))


def _diagonal_vec(front: Coord, side: Coord) -> Coord:
    return (_clamp_direction(front[0] + side[0]), _clamp_direction(front[1] + side[1]))


def apply_sensor_noise(
    value: int,
    max_range: int,
    rng: random.Random,
    p: float = 0.1,
    delta: int = 1,
) -> int:
    """Apply sparse +-delta noise while keeping values within [0, max_range]."""
    if rng.random() < p:
        value += rng.choice((-delta, delta))
    return max(0, min(max_range, value))


def read_sensors(
    origin: Coord,
    direction: int,
    width: int,
    height: int,
    obstacles: set[Coord],
    max_range: int = 10,
    sensor_noise_p: float = 0.0,
    rng: random.Random | None = None,
) -> SensorReading:
    front_vec = DIR_TO_VEC[direction]
    left_vec = DIR_TO_VEC[_rotate_left(direction)]
    right_vec = DIR_TO_VEC[_rotate_right(direction)]

    front = distance_to_block(origin, direction, width, height, obstacles, max_range=max_range)
    front_left = distance_to_block_vec(
        origin,
        _diagonal_vec(front_vec, left_vec),
        width,
        height,
        obstacles,
        max_range=max_range,
    )
    front_right = distance_to_block_vec(
        origin,
        _diagonal_vec(front_vec, right_vec),
        width,
        height,
        obstacles,
        max_range=max_range,
    )
    left = distance_to_block(origin, _rotate_left(direction), width, height, obstacles, max_range=max_range)
    right = distance_to_block(origin, _rotate_right(direction), width, height, obstacles, max_range=max_range)

    if rng is not None and sensor_noise_p > 0:
        front = apply_sensor_noise(front, max_range=max_range, rng=rng, p=sensor_noise_p)
        front_left = apply_sensor_noise(front_left, max_range=max_range, rng=rng, p=sensor_noise_p)
        front_right = apply_sensor_noise(front_right, max_range=max_range, rng=rng, p=sensor_noise_p)
        left = apply_sensor_noise(left, max_range=max_range, rng=rng, p=sensor_noise_p)
        right = apply_sensor_noise(right, max_range=max_range, rng=rng, p=sensor_noise_p)

    return SensorReading(
        front=front,
        front_left=front_left,
        front_right=front_right,
        left=left,
        right=right,
    )
