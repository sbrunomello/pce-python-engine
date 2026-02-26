from __future__ import annotations

from dataclasses import dataclass
import random
from uuid import uuid4

from .maps import generate_obstacles, random_free_cell
from .rewards import RewardInput, compute_step_reward
from .sensors import DIR_TO_VEC, SensorReading, read_sensors


@dataclass
class RobotState:
    x: int
    y: int
    direction: int
    energy: float = 100.0


@dataclass
class GoalState:
    x: int
    y: int


@dataclass
class WorldMetrics:
    tick: int = 0
    cumulative_reward: float = 0.0
    collisions: int = 0
    done: bool = False
    reason: str | None = None


class GridWorld:
    def __init__(
        self,
        width: int = 80,
        height: int = 60,
        seed: int = 42,
        max_steps: int = 2000,
        collision_limit: int = 20,
        sensor_range: int = 3,
        sensor_noise_p: float = 0.10,
        battery_max: float = 200.0,
        cost_move: float = 1.0,
        cost_turn: float = 0.5,
        cost_stop: float = 0.2,
    ) -> None:
        self.width = width
        self.height = height
        self.seed = seed
        self.max_steps = max_steps
        self.collision_limit = collision_limit
        self.episode_id = ""
        self.sensor_range = sensor_range
        self.sensor_noise_p = sensor_noise_p
        self.battery_max = battery_max
        self.cost_move = cost_move
        self.cost_turn = cost_turn
        self.cost_stop = cost_stop
        self._rng = random.Random(seed)
        self.obstacles: set[tuple[int, int]] = set()
        self.robot = RobotState(0, 0, 0)
        self.start = (0, 0)
        self.goal = GoalState(0, 0)
        self.metrics = WorldMetrics()
        self.last_reward = 0.0
        self.reset(seed)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        self.episode_id = str(uuid4())
        self.metrics = WorldMetrics()
        self._rng = random.Random(self.seed)
        self.obstacles = generate_obstacles(self.width, self.height, self.seed)
        start = random_free_cell(self.width, self.height, self.obstacles, self.seed + 1)
        goal = random_free_cell(self.width, self.height, self.obstacles | {start}, self.seed + 2)
        self.start = start
        self.robot = RobotState(start[0], start[1], direction=0, energy=self.battery_max)
        self.goal = GoalState(goal[0], goal[1])
        self.last_reward = 0.0

    def _distance(self) -> int:
        return abs(self.robot.x - self.goal.x) + abs(self.robot.y - self.goal.y)

    def sensors(self) -> SensorReading:
        return read_sensors(
            (self.robot.x, self.robot.y),
            self.robot.direction,
            self.width,
            self.height,
            self.obstacles,
            max_range=self.sensor_range,
            sensor_noise_p=self.sensor_noise_p,
            rng=self._rng,
        )

    def apply_action(self, action: dict[str, object]) -> None:
        if self.metrics.done:
            return
        action_type = str(action.get("type", "robot.stop"))
        prev_distance = self._distance()
        collision = False
        energy_cost = self.cost_stop

        if action_type == "robot.turn_left":
            energy_cost = self.cost_turn
            self.robot.direction = (self.robot.direction - 1) % 4
        elif action_type == "robot.turn_right":
            energy_cost = self.cost_turn
            self.robot.direction = (self.robot.direction + 1) % 4
        elif action_type == "robot.move_forward":
            amount = int(action.get("amount", 1))
            energy_cost = self.cost_move * max(1, amount)
            dx, dy = DIR_TO_VEC[self.robot.direction]
            target = (self.robot.x + dx * amount, self.robot.y + dy * amount)
            if (
                target[0] < 0
                or target[1] < 0
                or target[0] >= self.width
                or target[1] >= self.height
                or target in self.obstacles
            ):
                collision = True
                self.metrics.collisions += 1
            else:
                self.robot.x, self.robot.y = target

        self.robot.energy = max(0.0, self.robot.energy - energy_cost)

        self.metrics.tick += 1
        reached_goal = self.robot.x == self.goal.x and self.robot.y == self.goal.y
        battery_depleted = (not reached_goal) and self.robot.energy <= 0.0

        if reached_goal:
            self.metrics.done = True
            self.metrics.reason = "goal"
        elif self.metrics.tick >= self.max_steps:
            self.metrics.done = True
            self.metrics.reason = "timeout"
        elif self.metrics.collisions >= self.collision_limit:
            self.metrics.done = True
            self.metrics.reason = "collision"
        elif battery_depleted:
            self.metrics.done = True
            self.metrics.reason = "battery_depleted"

        current_distance = self._distance()
        step_reward = compute_step_reward(
            RewardInput(
                prev_distance=prev_distance,
                current_distance=current_distance,
                collision=collision,
                reached_goal=reached_goal,
                battery_depleted=self.metrics.done and self.metrics.reason == "battery_depleted",
            )
        )
        self.last_reward = step_reward
        self.metrics.cumulative_reward += step_reward

    def snapshot(self) -> dict[str, object]:
        return {
            "tick": self.metrics.tick,
            "episode_id": self.episode_id,
            "world": {
                "w": self.width,
                "h": self.height,
                "robot": {
                    "x": self.robot.x,
                    "y": self.robot.y,
                    "dir": self.robot.direction,
                    "energy": self.robot.energy,
                },
                "goal": {"x": self.goal.x, "y": self.goal.y},
                "start": {"x": self.start[0], "y": self.start[1]},
            },
            "metrics": {
                "reward": self.last_reward,
                "cumulative_reward": self.metrics.cumulative_reward,
                "distance": self._distance(),
                "collisions": self.metrics.collisions,
                "done": self.metrics.done,
                "reason": self.metrics.reason,
                "energy": self.robot.energy,
            },
        }
