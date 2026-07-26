from __future__ import annotations

import hashlib
import random

STREAMS = ("world", "scenario", "timeline", "traces", "documents", "quiz", "shuffle")


def derive_seed(master_seed: int, stream: str) -> int:
    digest = hashlib.sha256(f"{master_seed}:{stream}".encode()).hexdigest()
    return int(digest[:16], 16)


def derive_seeds(master_seed: int) -> dict[str, int]:
    return {stream: derive_seed(master_seed, stream) for stream in STREAMS}


def rng_for(master_seed: int, stream: str) -> random.Random:
    return random.Random(derive_seed(master_seed, stream))
