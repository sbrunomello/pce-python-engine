from agents.rover.world.sensors import read_sensors
from agents.rover.world.world import GridWorld


def test_front_diagonals_are_not_lateral_duplicates() -> None:
    # Empty map with robot centered and facing north.
    reading = read_sensors(
        origin=(3, 3),
        direction=0,
        width=10,
        height=10,
        obstacles={(2, 2), (4, 2)},
        max_range=3,
    )
    # Obstacles on diagonals should affect front-left/right without affecting lateral beams.
    assert reading.front_left < reading.left
    assert reading.front_right < reading.right


def test_read_sensors_respects_max_range() -> None:
    reading = read_sensors(
        origin=(5, 5),
        direction=1,
        width=100,
        height=100,
        obstacles=set(),
        max_range=2,
    )
    assert max(reading.front, reading.front_left, reading.front_right, reading.left, reading.right) <= 2


def test_world_sensors_use_world_sensor_range() -> None:
    world = GridWorld(width=30, height=30, seed=7, sensor_range=1, sensor_noise_p=0.0)
    world.robot.x = 10
    world.robot.y = 10
    world.obstacles = set()

    reading = world.sensors()
    assert max(reading.front, reading.front_left, reading.front_right, reading.left, reading.right) <= 1


def test_sensor_noise_is_deterministic_per_seed_and_episode() -> None:
    world_a = GridWorld(width=20, height=20, seed=11, sensor_range=3, sensor_noise_p=0.5)
    world_b = GridWorld(width=20, height=20, seed=11, sensor_range=3, sensor_noise_p=0.5)

    # Same world evolution should yield same noisy sensor sequence.
    seq_a = [world_a.sensors() for _ in range(8)]
    seq_b = [world_b.sensors() for _ in range(8)]
    assert seq_a == seq_b
