"""
backend/seed_manager.py
========================
Seed and reproducibility management.

The challenge requires that the same seed always produces the same dataset.

Usage
-----
    from backend.seed_manager import SeededRandom

    rng = SeededRandom(seed=20261022)
    val = rng.randint(1, 100)        # always same for same seed position

Design
------
* Wrap Python's ``random.Random`` (not the global random state) so that
  generation code never accidentally shares state with test code.
* Expose convenience helpers used throughout the generators.
* ``fork()`` creates a child RNG seeded deterministically from the parent —
  useful for independent sub-generators (students, programs, terms, …) that
  each need their own independent stream without cross-contaminating each other.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta
from typing import List, Optional, Sequence, TypeVar

T = TypeVar("T")


class SeededRandom:
    """
    A thin, self-contained wrapper around ``random.Random``.

    Parameters
    ----------
    seed : int
        Reproducibility seed.
    """

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Core delegation helpers
    # ------------------------------------------------------------------

    def randint(self, a: int, b: int) -> int:
        """Return random integer N such that a <= N <= b."""
        return self._rng.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._rng.choice(seq)

    def choices(
        self,
        population: Sequence[T],
        weights: Optional[Sequence[float]] = None,
        k: int = 1,
    ) -> List[T]:
        return self._rng.choices(population, weights=weights, k=k)

    def sample(self, population: Sequence[T], k: int) -> List[T]:
        return self._rng.sample(population, k)

    def shuffle(self, lst: list) -> None:
        self._rng.shuffle(lst)

    def random(self) -> float:
        """Return next random float in [0.0, 1.0)."""
        return self._rng.random()

    def weighted_choice(self, items: Sequence[T], weights: Sequence[float]) -> T:
        """Return one item from *items* according to *weights*."""
        return self._rng.choices(items, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    def random_date(self, start: date, end: date) -> date:
        """Return a random date between *start* and *end* inclusive."""
        delta = (end - start).days
        if delta < 0:
            raise ValueError(f"start ({start}) must be <= end ({end})")
        offset = self._rng.randint(0, delta)
        return start + timedelta(days=offset)

    def random_date_of_birth(
        self,
        min_age: int = 17,
        max_age: int = 35,
        reference: Optional[date] = None,
    ) -> date:
        """
        Return a plausible student date of birth.

        Parameters
        ----------
        min_age, max_age : int
            Age range in years.
        reference : date | None
            Reference date for age calculation (defaults to 2024-01-01).
        """
        ref = reference or date(2024, 1, 1)
        earliest = date(ref.year - max_age, 1, 1)
        latest = date(ref.year - min_age, 12, 31)
        return self.random_date(earliest, latest)

    # ------------------------------------------------------------------
    # Fork — deterministic child RNG
    # ------------------------------------------------------------------

    def fork(self, label: str) -> "SeededRandom":
        """
        Create a deterministic child RNG seeded from this RNG's current state
        combined with *label*.

        This lets each generator sub-module (programs, students, terms, …)
        have its own independent stream, so adding a new sub-generator does
        not shift all subsequent sub-generators.

        Parameters
        ----------
        label : str
            A unique string label for this child stream.
        """
        # Derive a child seed deterministically without consuming parent state
        seed_material = f"{self._seed}:{label}".encode("utf-8")
        child_seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "big")
        return SeededRandom(seed=child_seed)

    @property
    def seed(self) -> int:
        return self._seed
