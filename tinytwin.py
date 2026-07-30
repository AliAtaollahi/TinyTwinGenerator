#!/usr/bin/env python3
"""Generate a TinyTwin from a Rebeca state-space file."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence

from cast_and_extract import (
    cast_state_space,
    hide_non_observable_actions,
    read_observable_actions,
)
from lts_reduction import LTS, read_aut, reduce_lts, write_aut, write_dot
from time_accumulator import accumulate_time


EQUIVALENCES = ("weak-trace", "weak-bisim")


def _cast(statespace: Path, observable_actions: Path) -> LTS:
    state_count, transitions = cast_state_space(statespace)
    observable = read_observable_actions(observable_actions)
    hidden = hide_non_observable_actions(transitions, observable)
    return LTS.create(0, state_count, hidden)


def _internal_pipeline(cast_lts: LTS, equivalence: str) -> LTS:
    raw = reduce_lts(cast_lts, equivalence)
    timed = accumulate_time(raw)
    return reduce_lts(timed, equivalence)


def _run_ltsconvert(
    executable: str,
    input_path: Path,
    output_path: Path,
    equivalence: str | None = None,
) -> None:
    command = [executable]
    if equivalence is not None:
        command.append(f"--equivalence={equivalence}")
    command.extend([str(input_path), str(output_path)])
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"ltsconvert failed with exit code {result.returncode}"
            + (f": {details}" if details else "")
        )


def _mcrl2_pipeline(
    cast_lts: LTS,
    equivalence: str,
    output_aut: Path,
    output_dot: Path,
) -> None:
    executable = shutil.which("ltsconvert")
    if executable is None:
        raise RuntimeError(
            "--mcrl2 was requested, but ltsconvert was not found in PATH"
        )

    with tempfile.TemporaryDirectory(prefix="tinytwin-") as temporary:
        work = Path(temporary)
        cast_path = work / "cast.aut"
        raw_path = work / "raw.aut"
        timed_path = work / "timed.aut"

        write_aut(cast_lts, cast_path)
        _run_ltsconvert(executable, cast_path, raw_path, equivalence)
        write_aut(accumulate_time(read_aut(raw_path)), timed_path)
        _run_ltsconvert(executable, timed_path, output_aut, equivalence)
        _run_ltsconvert(executable, output_aut, output_dot)


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate tinytwin.aut and tinytwin.dot using the built-in "
            "weak-equivalence reductions."
        )
    )
    parser.add_argument("statespace", type=Path)
    parser.add_argument("observable_actions", type=Path)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.cwd(),
        help="output directory (default: current directory)",
    )
    parser.add_argument(
        "-e",
        "--equivalence",
        choices=EQUIVALENCES,
        default="weak-trace",
        help="reduction to apply before and after time accumulation",
    )
    parser.add_argument(
        "--mcrl2",
        action="store_true",
        help="use mCRL2 ltsconvert instead of the built-in implementation",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
    try:
        if not arguments.statespace.is_file():
            raise ValueError(
                f"state-space file not found: {arguments.statespace}"
            )
        if not arguments.observable_actions.is_file():
            raise ValueError(
                "observable-actions file not found: "
                f"{arguments.observable_actions}"
            )

        arguments.output.mkdir(parents=True, exist_ok=True)
        output_aut = arguments.output / "tinytwin.aut"
        output_dot = arguments.output / "tinytwin.dot"
        cast_lts = _cast(arguments.statespace, arguments.observable_actions)

        if arguments.mcrl2:
            _mcrl2_pipeline(
                cast_lts,
                arguments.equivalence,
                output_aut,
                output_dot,
            )
        else:
            result = _internal_pipeline(cast_lts, arguments.equivalence)
            write_aut(result, output_aut)
            write_dot(result, output_dot)

        print("Generated:")
        print(output_aut)
        print(output_dot)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
