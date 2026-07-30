#!/usr/bin/env python3
"""Collapse consecutive AUT time transitions into accumulated transitions."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re
import sys
from typing import Sequence

from lts_reduction import LTS, read_aut, write_aut_preserving_order


_TIME_RE = re.compile(r"^\s*time\s*\+=\s*(\d+)\s*$", re.IGNORECASE)


def time_increment(label: str) -> int | None:
    match = _TIME_RE.match(label)
    return int(match.group(1)) if match else None


def accumulate_time(lts: LTS) -> LTS:
    """Replace maximal acyclic time-only paths with their total duration.

    A path starts at the initial state or immediately after a non-time action,
    and ends at a state without an outgoing time transition. All non-time
    transitions are retained in input order, followed by accumulated paths in
    discovery order. Cyclic time-only paths have no finite terminal duration
    and are therefore not emitted.
    """

    time_out: dict[int, list[tuple[int, int]]] = defaultdict(list)
    time_in_count: dict[int, int] = defaultdict(int)
    non_time_predecessors: dict[int, list[int]] = defaultdict(list)
    non_time_transitions: list[tuple[int, str, int]] = []

    for source, label, target in lts.transitions:
        increment = time_increment(label)
        if increment is None:
            non_time_transitions.append((source, label, target))
            non_time_predecessors[target].append(source)
        else:
            time_out[source].append((increment, target))
            time_in_count[target] += 1

    reachable = {lts.initial_state}
    pending = [lts.initial_state]
    successors: dict[int, list[int]] = defaultdict(list)
    for source, _label, target in lts.transitions:
        successors[source].append(target)
    while pending:
        source = pending.pop()
        for target in successors[source]:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)

    entries = [
        state
        for state in time_out
        if state in reachable
        and (
            state == lts.initial_state
            or any(
                predecessor in reachable
                for predecessor in non_time_predecessors[state]
            )
            or time_in_count[state] == 0
        )
    ]

    accumulated: list[tuple[int, str, int]] = []
    seen_accumulated: set[tuple[int, int, int]] = set()

    def follow(
        start: int,
        state: int,
        total: int,
        visited: frozenset[int],
    ) -> None:
        outgoing = time_out.get(state, [])
        if not outgoing:
            identity = (start, total, state)
            if state != start and identity not in seen_accumulated:
                seen_accumulated.add(identity)
                accumulated.append((start, f"time +={total}", state))
            return
        for increment, target in outgoing:
            if target not in visited:
                follow(start, target, total + increment, visited | {target})

    for entry in entries:
        for increment, target in time_out[entry]:
            follow(entry, target, increment, frozenset({entry, target}))

    return LTS.create(
        lts.initial_state,
        lts.num_states,
        [*non_time_transitions, *accumulated],
    )


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collapse consecutive time transitions in an AUT file."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
    try:
        result = accumulate_time(read_aut(arguments.input))
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        write_aut_preserving_order(result, arguments.output)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
