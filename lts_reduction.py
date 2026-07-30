#!/usr/bin/env python3
"""Finite labelled-transition-system algorithms used by TinyTwin.

The reductions in this module follow the algorithms used by mCRL2:

* weak trace: remove silent behaviour with tau closure, determinise, and
  minimise modulo strong bisimulation;
* weak bisimulation: saturate the LTS with ``tau* a tau*`` transitions,
  minimise modulo strong bisimulation, then remove redundant tau transitions.

The implementation is intentionally dependency-free so that TinyTwin can run
on Python alone on Windows and Linux.

Algorithm reference: mCRL2 202407.1, in particular ``lts_algorithm.h``,
``detail/liblts_tau_star_reduce.h``, and ``detail/liblts_weak_bisim.h``.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Iterator


TAU = "tau"
Transition = tuple[int, str, int]


@dataclass(frozen=True)
class LTS:
    """A finite labelled transition system."""

    initial_state: int
    num_states: int
    transitions: tuple[Transition, ...]

    @classmethod
    def create(
        cls,
        initial_state: int,
        num_states: int,
        transitions: Iterable[Transition],
    ) -> "LTS":
        return cls(initial_state, num_states, tuple(transitions))


def _check_lts(lts: LTS) -> None:
    if lts.num_states <= 0:
        raise ValueError("an LTS must contain at least one state")
    if not 0 <= lts.initial_state < lts.num_states:
        raise ValueError(f"invalid initial state {lts.initial_state}")
    for source, _label, target in lts.transitions:
        if not 0 <= source < lts.num_states:
            raise ValueError(f"invalid transition source {source}")
        if not 0 <= target < lts.num_states:
            raise ValueError(f"invalid transition target {target}")


def canonicalize(lts: LTS) -> LTS:
    """Remove unreachable states and assign stable breadth-first state numbers."""

    _check_lts(lts)
    outgoing: list[set[tuple[str, int]]] = [
        set() for _ in range(lts.num_states)
    ]
    for source, label, target in lts.transitions:
        outgoing[source].add((label, target))

    state_map = {lts.initial_state: 0}
    pending = deque([lts.initial_state])
    while pending:
        source = pending.popleft()
        for _label, target in sorted(outgoing[source]):
            if target not in state_map:
                state_map[target] = len(state_map)
                pending.append(target)

    transitions = {
        (state_map[source], label, state_map[target])
        for source, edges in enumerate(outgoing)
        if source in state_map
        for label, target in edges
        if target in state_map
    }
    return LTS.create(0, len(state_map), sorted(transitions))


def strong_bisimulation_reduce(lts: LTS) -> LTS:
    """Return the quotient under strong bisimulation."""

    lts = canonicalize(lts)
    outgoing: list[set[tuple[str, int]]] = [
        set() for _ in range(lts.num_states)
    ]
    for source, label, target in lts.transitions:
        outgoing[source].add((label, target))

    blocks = [0] * lts.num_states
    while True:
        signatures: list[tuple[int, tuple[tuple[str, int], ...]]] = []
        for state in range(lts.num_states):
            behaviour = tuple(
                sorted(
                    {
                        (label, blocks[target])
                        for label, target in outgoing[state]
                    }
                )
            )
            signatures.append((blocks[state], behaviour))

        signature_ids: dict[tuple[int, tuple[tuple[str, int], ...]], int] = {}
        new_blocks: list[int] = []
        for signature in signatures:
            if signature not in signature_ids:
                signature_ids[signature] = len(signature_ids)
            new_blocks.append(signature_ids[signature])

        if new_blocks == blocks:
            break
        blocks = new_blocks

    transitions = {
        (blocks[source], label, blocks[target])
        for source, label, target in lts.transitions
    }
    return canonicalize(
        LTS.create(blocks[lts.initial_state], max(blocks) + 1, transitions)
    )


def _finish_order(adjacency: list[set[int]]) -> list[int]:
    """Return DFS finish order without depending on Python's recursion limit."""

    visited: set[int] = set()
    order: list[int] = []
    for root in range(len(adjacency)):
        if root in visited:
            continue
        visited.add(root)
        stack: list[tuple[int, Iterator[int]]] = [
            (root, iter(sorted(adjacency[root])))
        ]
        while stack:
            state, children = stack[-1]
            try:
                target = next(children)
            except StopIteration:
                order.append(state)
                stack.pop()
                continue
            if target not in visited:
                visited.add(target)
                stack.append((target, iter(sorted(adjacency[target]))))
    return order


def _tau_sccs(lts: LTS) -> tuple[list[int], int]:
    adjacency: list[set[int]] = [set() for _ in range(lts.num_states)]
    reverse: list[set[int]] = [set() for _ in range(lts.num_states)]
    for source, label, target in lts.transitions:
        if label == TAU:
            adjacency[source].add(target)
            reverse[target].add(source)

    component = [-1] * lts.num_states
    component_count = 0
    for root in reversed(_finish_order(adjacency)):
        if component[root] != -1:
            continue
        component[root] = component_count
        pending = [root]
        while pending:
            state = pending.pop()
            for target in reverse[state]:
                if component[target] == -1:
                    component[target] = component_count
                    pending.append(target)
        component_count += 1
    return component, component_count


def _collapse_tau_sccs(lts: LTS) -> LTS:
    """Collapse mutually tau-reachable states and remove internal tau loops."""

    lts = canonicalize(lts)
    component, component_count = _tau_sccs(lts)
    transitions = {
        (component[source], label, component[target])
        for source, label, target in lts.transitions
        if label != TAU or component[source] != component[target]
    }
    return canonicalize(
        LTS.create(component[lts.initial_state], component_count, transitions)
    )


def _tau_closures(lts: LTS) -> list[frozenset[int]]:
    """Calculate reflexive transitive tau closure on a tau DAG."""

    successors: list[set[int]] = [set() for _ in range(lts.num_states)]
    indegree = [0] * lts.num_states
    for source, label, target in lts.transitions:
        if label == TAU and target not in successors[source]:
            successors[source].add(target)
            indegree[target] += 1

    ready = deque(state for state, degree in enumerate(indegree) if degree == 0)
    topological: list[int] = []
    while ready:
        state = ready.popleft()
        topological.append(state)
        for target in successors[state]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)

    if len(topological) != lts.num_states:
        raise ValueError("tau graph is not acyclic after SCC reduction")

    closures: list[set[int]] = [{state} for state in range(lts.num_states)]
    for source in reversed(topological):
        for target in successors[source]:
            closures[source].update(closures[target])
    return [frozenset(closure) for closure in closures]


def weak_trace_reduce(lts: LTS) -> LTS:
    """Return a canonical deterministic representative of weak traces."""

    lts = _collapse_tau_sccs(lts)
    closures = _tau_closures(lts)
    visible: list[list[tuple[str, int]]] = [
        [] for _ in range(lts.num_states)
    ]
    for source, label, target in lts.transitions:
        if label != TAU:
            visible[source].append((label, target))

    initial = closures[lts.initial_state]
    subset_ids: dict[frozenset[int], int] = {initial: 0}
    pending = deque([initial])
    transitions: set[Transition] = set()
    while pending:
        source_subset = pending.popleft()
        by_label: dict[str, set[int]] = defaultdict(set)
        for state in source_subset:
            for label, target in visible[state]:
                by_label[label].update(closures[target])

        source_id = subset_ids[source_subset]
        for label in sorted(by_label):
            target_subset = frozenset(by_label[label])
            if target_subset not in subset_ids:
                subset_ids[target_subset] = len(subset_ids)
                pending.append(target_subset)
            transitions.add((source_id, label, subset_ids[target_subset]))

    deterministic = LTS.create(0, len(subset_ids), transitions)
    return strong_bisimulation_reduce(deterministic)


def _weakly_saturate(lts: LTS) -> LTS:
    """Add the ``tau*`` and ``tau* a tau*`` transitions used by mCRL2."""

    closures = _tau_closures(lts)
    visible: list[list[tuple[str, int]]] = [
        [] for _ in range(lts.num_states)
    ]
    for source, label, target in lts.transitions:
        if label != TAU:
            visible[source].append((label, target))

    transitions: set[Transition] = set()
    for source in range(lts.num_states):
        for target in closures[source]:
            transitions.add((source, TAU, target))
        for prefix_state in closures[source]:
            for label, middle_target in visible[prefix_state]:
                for target in closures[middle_target]:
                    transitions.add((source, label, target))
    return LTS.create(lts.initial_state, lts.num_states, transitions)


def _remove_redundant_weak_transitions(lts: LTS) -> LTS:
    """Apply the two redundancy rules used after mCRL2 weak reduction."""

    lts = canonicalize(lts)
    outgoing: list[dict[str, set[int]]] = [
        defaultdict(set) for _ in range(lts.num_states)
    ]
    for source, label, target in lts.transitions:
        outgoing[source][label].add(target)

    retained: set[Transition] = set()
    for source, label, target in lts.transitions:
        redundant = any(
            target in outgoing[after_tau].get(label, set())
            for after_tau in outgoing[source].get(TAU, set())
        )
        if not redundant and label != TAU:
            redundant = any(
                target in outgoing[after_label].get(TAU, set())
                for after_label in outgoing[source].get(label, set())
            )
        if not redundant:
            retained.add((source, label, target))
    return canonicalize(
        LTS.create(lts.initial_state, lts.num_states, retained)
    )


def weak_bisimulation_reduce(lts: LTS) -> LTS:
    """Return the divergence-insensitive weak-bisimulation quotient."""

    condensed = _collapse_tau_sccs(lts)
    saturated = _weakly_saturate(condensed)
    reduced = strong_bisimulation_reduce(saturated)
    without_tau_loops = _collapse_tau_sccs(reduced)
    return _remove_redundant_weak_transitions(without_tau_loops)


def reduce_lts(lts: LTS, equivalence: str) -> LTS:
    if equivalence == "weak-trace":
        return weak_trace_reduce(lts)
    if equivalence == "weak-bisim":
        return weak_bisimulation_reduce(lts)
    raise ValueError(f"unsupported equivalence: {equivalence}")


_AUT_HEADER_RE = re.compile(
    r"^\s*des\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*$"
)
_AUT_TRANSITION_RE = re.compile(
    r'^\s*\(\s*(\d+)\s*,\s*"((?:\\.|[^"\\])*)"\s*,\s*(\d+)\s*\)\s*$'
)


def _escape_label(label: str) -> str:
    return label.replace("\\", "\\\\").replace('"', '\\"')


def _unescape_label(label: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(label):
        if label[index] == "\\" and index + 1 < len(label):
            index += 1
        result.append(label[index])
        index += 1
    return "".join(result)


def parse_aut(text: str) -> LTS:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty AUT input")
    header = _AUT_HEADER_RE.match(lines[0])
    if not header:
        raise ValueError(f"invalid AUT header: {lines[0]!r}")

    initial_state = int(header.group(1))
    expected_transitions = int(header.group(2))
    num_states = int(header.group(3))
    transitions: list[Transition] = []
    for line in lines[1:]:
        match = _AUT_TRANSITION_RE.match(line)
        if not match:
            raise ValueError(f"invalid AUT transition: {line!r}")
        transitions.append(
            (
                int(match.group(1)),
                _unescape_label(match.group(2)),
                int(match.group(3)),
            )
        )
    if len(transitions) != expected_transitions:
        raise ValueError(
            f"AUT header declares {expected_transitions} transitions, "
            f"but {len(transitions)} were read"
        )
    return LTS.create(initial_state, num_states, transitions)


def read_aut(path: str | Path) -> LTS:
    return parse_aut(Path(path).read_text(encoding="utf-8"))


def format_aut(lts: LTS) -> str:
    lts = canonicalize(lts)
    return format_aut_preserving_order(lts)


def format_aut_preserving_order(lts: LTS) -> str:
    """Format AUT without renumbering or reordering its transitions."""

    _check_lts(lts)
    lines = [
        f"des ({lts.initial_state},{len(lts.transitions)},{lts.num_states})"
    ]
    lines.extend(
        f'({source},"{_escape_label(label)}",{target})'
        for source, label, target in lts.transitions
    )
    return "\n".join(lines) + "\n"


def write_aut(lts: LTS, path: str | Path) -> None:
    Path(path).write_text(format_aut(lts), encoding="utf-8")


def write_aut_preserving_order(lts: LTS, path: str | Path) -> None:
    Path(path).write_text(
        format_aut_preserving_order(lts),
        encoding="utf-8",
    )


def format_dot(lts: LTS) -> str:
    lts = canonicalize(lts)
    lines = [
        "digraph G {",
        "center = TRUE;",
        "mclimit = 10.0;",
        "nodesep = 0.05;",
        'node [ width=0.25, height=0.25, label="" ];',
    ]
    for state in range(lts.num_states):
        if state == lts.initial_state:
            lines.append(f"S{state} [ peripheries=2 ];")
        else:
            lines.append(f"S{state}")
    for source, label, target in lts.transitions:
        lines.append(
            f'S{source} -> S{target}[label="{_escape_label(label)}"];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_dot(lts: LTS, path: str | Path) -> None:
    Path(path).write_text(format_dot(lts), encoding="utf-8")
