"""Rolling cooking-temperature estimate."""

import math
from collections import deque


class TemperatureTrend:
    """Five-minute linear trend, resetting on disconnects or long data gaps."""

    def __init__(self):
        self.samples = deque()

    def add(self, timestamp, temperature):
        if temperature is None or not math.isfinite(temperature):
            self.samples.clear()
            return
        if self.samples and timestamp - self.samples[-1][0] > 90:
            self.samples.clear()
        if self.samples and timestamp <= self.samples[-1][0]:
            return
        self.samples.append((timestamp, temperature))
        while self.samples and timestamp - self.samples[0][0] > 300:
            self.samples.popleft()

    def minutes_to_target(self, target, now):
        if not self.samples or target is None or not math.isfinite(target):
            return None
        timestamp, current = self.samples[-1]
        if now - timestamp > 90:
            return None
        if current >= target:
            return 0
        if len(self.samples) < 3 or timestamp - self.samples[0][0] < 60:
            return None
        origin = self.samples[0][0]
        xs = [(stamp - origin) / 60 for stamp, _ in self.samples]
        ys = [temperature for _, temperature in self.samples]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        rate = (
            sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
            / denominator
        )
        return round((target - current) / rate, 1) if rate > 0.01 else None
