import argparse
import time

from .sandbox import tick

p = argparse.ArgumentParser()
p.add_argument("experiment")
p.add_argument("--ticks", type=int, default=1)
a = p.parse_args()
for _ in range(min(a.ticks, 30)):
    tick(a.experiment)
    time.sleep(0.2)
