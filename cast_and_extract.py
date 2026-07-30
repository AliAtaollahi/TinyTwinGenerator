#!/usr/bin/env python3
"""Cast a Rebeca state space to AUT and hide non-observable messages."""

from __future__ import annotations

import argparse
import collections
import re
import sys
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from pathlib import Path
from typing import Counter, DefaultDict, Dict, Iterable, List, Sequence, Tuple


Transition = Tuple[int, str, int]
_QUALIFIED_MESSAGE_RE = re.compile(
    r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$",
    re.IGNORECASE,
)
_TIME_LABEL_RE = re.compile(r"^\s*time\s*\+=\s*\d+\s*$", re.IGNORECASE)


def state_number(raw_id: str, context: str) -> int:
    """Convert Rebeca's one-based ``N_suffix`` state IDs to zero-based IDs."""
    number = raw_id.split("_", 1)[0]
    try:
        result = int(number) - 1
    except ValueError as error:
        raise ValueError(f"{context} has an invalid state ID: {raw_id!r}") from error
    if result < 0:
        raise ValueError(f"{context} has an invalid state ID: {raw_id!r}")
    return result


def queued_messages(state: ElementTree.Element) -> List[str]:
    return [
        (message.text or "").strip()
        for message in state.iter("message")
        if (message.text or "").strip()
    ]


def state_variables(state: ElementTree.Element) -> Dict[str, str]:
    variables: Dict[str, str] = {}
    for variable in state.iter("variable"):
        name = variable.get("name")
        if name is None:
            raise ValueError("A <variable> is missing its name attribute")
        variables[name] = (variable.text or "").strip()
    return variables


def message_arguments(message: str) -> List[str]:
    opening = message.find("(")
    closing = message.rfind(")")
    if opening < 0 or closing < opening:
        return []
    return [value.strip() for value in message[opening + 1 : closing].split(",")]


def added_message_arguments(
    source_messages: Sequence[str], destination_messages: Sequence[str]
) -> List[str]:
    source_counts: Counter[str] = collections.Counter(source_messages)
    destination_counts: Counter[str] = collections.Counter(destination_messages)
    added_messages = list((destination_counts - source_counts).elements())
    return [
        argument
        for message in added_messages
        for argument in message_arguments(message)
        if argument
    ]


def add_action_values(label: str, values: Sequence[str]) -> str:
    """Append values to the message-argument brackets in an action label."""
    annotation_separator = label.rfind("].[")
    if annotation_separator < 0:
        raise ValueError(f"Cannot annotate malformed action label: {label!r}")
    action = label[: annotation_separator + 1]
    variable_annotation = label[annotation_separator + 1 :]
    opening = action.rfind("[")
    existing_values = action[opening + 1 : -1]
    combined = ",".join(
        value for value in [existing_values, *values] if value
    )
    return f"{action[:opening]}[{combined}]{variable_annotation}"


def nondeterministic_action_values(
    transition_indexes: Sequence[int],
    transitions: Sequence[ElementTree.Element],
    messages_by_state: Dict[int, List[str]],
    variables_by_state: Dict[int, Dict[str, str]],
) -> Dict[int, List[str]]:
    """Find branch-result values that distinguish otherwise identical edges.

    Rebeca represents a nondeterministic assignment as multiple same-action
    transitions from one source. A changed value is externally relevant when
    each branch propagates that value as an argument of a newly queued message.
    If only one state variable differs, it is unambiguous even without such a
    message.
    """
    if len(transition_indexes) < 2:
        return {}

    destinations = [
        state_number(
            transitions[index].get("destination", ""),
            f"Transition {index + 1} destination",
        )
        for index in transition_indexes
    ]
    if len(set(destinations)) < 2:
        return {}

    source = state_number(
        transitions[transition_indexes[0]].get("source", ""),
        f"Transition {transition_indexes[0] + 1} source",
    )
    variable_names = list(variables_by_state[source])
    varying_variables = [
        name
        for name in variable_names
        if len(
            {
                variables_by_state[destination].get(name)
                for destination in destinations
            }
        )
        > 1
    ]
    if not varying_variables:
        return {}

    propagated_arguments = [
        set(
            added_message_arguments(
                messages_by_state[source], messages_by_state[destination]
            )
        )
        for destination in destinations
    ]
    selected_variables = [
        name
        for name in varying_variables
        if all(
            variables_by_state[destination].get(name) in propagated_arguments[position]
            for position, destination in enumerate(destinations)
        )
    ]
    if not selected_variables and len(varying_variables) == 1:
        selected_variables = varying_variables
    if not selected_variables:
        return {}

    return {
        index: [
            variables_by_state[destination][name] for name in selected_variables
        ]
        for index, destination in zip(transition_indexes, destinations)
    }


def action_label(
    message_server: ElementTree.Element, source_messages: Sequence[str]
) -> str:
    """Reproduce the labels emitted by the original LF/C++ caster."""
    owner = message_server.get("owner")
    title = message_server.get("title")
    if owner is None or title is None:
        raise ValueError("A <messageserver> needs both owner and title attributes")

    selected_title = title.lower()
    for queued_message in source_messages:
        if selected_title in queued_message.lower():
            selected_title = queued_message
            break

    return (
        f"{owner}.{selected_title}".lower().replace("(", "[").replace(")", "]")
        + ".[]"
    )


def transition_label(
    transition: ElementTree.Element, source_messages: Sequence[str]
) -> str:
    time_element = transition.find("time")
    if time_element is not None:
        value = time_element.get("value")
        if value is None:
            raise ValueError("A <time> transition needs a value attribute")
        return f"time +={value}"

    message_server = transition.find("messageserver")
    if message_server is None:
        raise ValueError(
            "Every <transition> needs a <time> or <messageserver> child"
        )
    return action_label(message_server, source_messages)


def cast_state_space(path: Path) -> Tuple[int, List[Transition]]:
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as error:
        raise ValueError(f"Invalid XML in {path}: {error}") from error

    if root.tag != "transitionsystem":
        raise ValueError(
            f"Expected <transitionsystem> in {path}, found <{root.tag}>"
        )

    states = root.findall("state")
    if not states:
        raise ValueError(f"No <state> elements found in {path}")

    messages_by_state: Dict[int, List[str]] = {}
    variables_by_state: Dict[int, Dict[str, str]] = {}
    for state in states:
        raw_id = state.get("id")
        if raw_id is None:
            raise ValueError("A <state> is missing its id attribute")
        state_id = state_number(raw_id, "State")
        if state_id in messages_by_state:
            raise ValueError(f"Duplicate state ID: {raw_id!r}")
        messages_by_state[state_id] = queued_messages(state)
        variables_by_state[state_id] = state_variables(state)

    expected_ids = set(range(len(states)))
    actual_ids = set(messages_by_state)
    if actual_ids != expected_ids:
        raise ValueError(
            "State IDs must be consecutive and start at 1 "
            f"(found zero-based IDs {sorted(actual_ids)})"
        )

    xml_transitions = root.findall("transition")
    base_labels: List[str] = []
    duplicate_action_groups: DefaultDict[Tuple[int, str], List[int]] = defaultdict(
        list
    )
    for index, transition in enumerate(xml_transitions):
        raw_source = transition.get("source")
        if raw_source is None:
            raise ValueError(f"Transition {index + 1} needs a source attribute")
        source = state_number(raw_source, f"Transition {index + 1} source")
        label = transition_label(transition, messages_by_state[source])
        base_labels.append(label)
        if transition.find("messageserver") is not None:
            duplicate_action_groups[(source, label)].append(index)

    annotations: Dict[int, List[str]] = {}
    for transition_indexes in duplicate_action_groups.values():
        annotations.update(
            nondeterministic_action_values(
                transition_indexes,
                xml_transitions,
                messages_by_state,
                variables_by_state,
            )
        )

    transitions_by_source: DefaultDict[int, List[Tuple[str, int]]] = defaultdict(list)
    next_intermediate_state = len(states)

    for index, transition in enumerate(xml_transitions, start=1):
        raw_source = transition.get("source")
        raw_destination = transition.get("destination")
        if raw_source is None or raw_destination is None:
            raise ValueError(
                f"Transition {index} needs source and destination attributes"
            )

        source = state_number(raw_source, f"Transition {index} source")
        destination = state_number(
            raw_destination, f"Transition {index} destination"
        )
        if source not in messages_by_state or destination not in messages_by_state:
            raise ValueError(
                f"Transition {index} refers to an unknown state "
                f"({raw_source!r} -> {raw_destination!r})"
            )

        label = base_labels[index - 1]
        if index - 1 in annotations:
            label = add_action_values(label, annotations[index - 1])
        raw_shift = transition.get("shift", "0")
        raw_execution_time = transition.get("executionTime", "0")
        try:
            shift = int(raw_shift)
        except ValueError as error:
            raise ValueError(
                f"Transition {index} has an invalid shift: {raw_shift!r}"
            ) from error

        if shift:
            intermediate = next_intermediate_state
            next_intermediate_state += 1
            transitions_by_source[source].append((label, intermediate))
            transitions_by_source[intermediate].append(
                (f"@[{raw_execution_time}>>{raw_shift}]", destination)
            )
        else:
            transitions_by_source[source].append((label, destination))

    result: List[Transition] = []
    for source in range(next_intermediate_state):
        for label, destination in transitions_by_source[source]:
            result.append((source, label, destination))
    return next_intermediate_state, result


def escape_aut_label(label: str) -> str:
    return label.replace("\\", "\\\\").replace('"', '\\"')


def format_aut(state_count: int, transitions: Iterable[Transition]) -> str:
    materialized = list(transitions)
    lines = [f"des(0,{len(materialized)},{state_count})"]
    lines.extend(
        f'({source},"{escape_aut_label(label)}",{destination})'
        for source, label, destination in materialized
    )
    return "\n".join(lines) + "\n"


def read_observable_messages(path: Path) -> List[str]:
    """Read and validate exact ``owner.message`` selectors.

    Message arguments are deliberately absent from a selector. ``time`` is
    the only unqualified selector because time progress has no message owner.
    """

    text = path.read_text(encoding="utf-8")
    messages = [
        item.strip().lower()
        for item in re.split(r"[,\r\n]+", text)
        if item.strip()
    ]
    if not messages:
        raise ValueError(f"Observable-message file is empty: {path}")
    invalid = [
        message
        for message in messages
        if message != "time"
        and _QUALIFIED_MESSAGE_RE.fullmatch(message) is None
    ]
    if invalid:
        raise ValueError(
            "Observable messages must use owner.message format "
            "(or the reserved entry 'time'): "
            + ", ".join(invalid)
        )
    if len(set(messages)) != len(messages):
        raise ValueError("Duplicate observable message")
    return messages


def message_selector(label: str) -> str | None:
    """Return ``owner.message`` or ``time`` for a generated transition label."""

    if _TIME_LABEL_RE.fullmatch(label):
        return "time"
    argument_start = label.find("[")
    if argument_start < 0:
        return None
    selector = label[:argument_start].strip().lower()
    if _QUALIFIED_MESSAGE_RE.fullmatch(selector) is None:
        return None
    return selector


def hide_non_observable_messages(
    transitions: Iterable[Transition], observable_messages: Sequence[str]
) -> List[Transition]:
    """Replace every label not selected by exact owner and message with tau."""

    selected = {message.lower() for message in observable_messages}
    return [
        (
            source,
            label
            if message_selector(label) in selected
            else "tau",
            destination,
        )
        for source, label, destination in transitions
    ]


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cast a Rebeca .statespace file to AUT and replace actions that "
            "are not listed as observable owner.message entries with tau."
        )
    )
    parser.add_argument("statespace", type=Path)
    parser.add_argument("observable_messages", type=Path)
    parser.add_argument(
        "--aut-output", required=True, type=Path, help="path for the cast AUT file"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
    try:
        state_count, transitions = cast_state_space(arguments.statespace)
        observable = read_observable_messages(
            arguments.observable_messages
        )
        transitions = hide_non_observable_messages(
            transitions,
            observable,
        )

        arguments.aut_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.aut_output.write_text(
            format_aut(state_count, transitions), encoding="utf-8"
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
