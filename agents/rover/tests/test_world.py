from agents.rover.world.world import GridWorld


def test_turn_changes_direction() -> None:
    world = GridWorld(width=10, height=10, seed=1)
    start = world.robot.direction
    world.apply_action({"type": "robot.turn_left"})
    assert world.robot.direction == (start - 1) % 4
    world.apply_action({"type": "robot.turn_right"})
    assert world.robot.direction == start


def test_move_forward_respects_obstacles_and_bounds() -> None:
    world = GridWorld(width=5, height=5, seed=1)
    world.obstacles = {(1, 0)}
    world.robot.x = 0
    world.robot.y = 0
    world.robot.direction = 1
    world.apply_action({"type": "robot.move_forward", "amount": 1})
    assert (world.robot.x, world.robot.y) == (0, 0)
    assert world.metrics.collisions == 1


def test_done_goal_and_timeout() -> None:
    world = GridWorld(width=5, height=5, seed=1, max_steps=2)
    world.goal.x = world.robot.x
    world.goal.y = world.robot.y
    world.apply_action({"type": "robot.stop"})
    assert world.metrics.done is True
    assert world.metrics.reason == "goal"

    timeout_world = GridWorld(width=5, height=5, seed=2, max_steps=1)
    timeout_world.apply_action({"type": "robot.stop"})
    assert timeout_world.metrics.done is True
    assert timeout_world.metrics.reason == "timeout"
