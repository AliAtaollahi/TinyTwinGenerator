from __future__ import annotations

from pathlib import Path
import re
import unittest

from cast_and_extract import (
    cast_state_space,
    hide_non_observable_actions,
    read_observable_actions,
)
from lts_reduction import (
    LTS,
    format_aut,
    parse_aut,
    weak_bisimulation_reduce,
    weak_trace_reduce,
)
from time_accumulator import accumulate_time
from tinytwin import _internal_pipeline


# Regression models and expected quotient sizes from mCRL2 202407.1's
# libraries/lts/test/ltsconvert_test.cpp.
MCRL2_WEAK_BISIM_CASES = {
    "tau cycle": (
        """\
des (0,3,2)
(0,"tau",1)
(1,"tau",0)
(0,"a",1)
""",
        (1, 1),
    ),
    "tau choice": (
        """\
des (0,5,6)
(0,"a",1)
(1,"tau",2)
(2,"b",3)
(2,"c",4)
(1,"b",5)
""",
        (3, 3),
    ),
    "third tau law": (
        """\
des (0,6,7)
(0,"a",1)
(0,"a",2)
(1,"tau",3)
(1,"c",4)
(3,"b",5)
(2,"b",6)
""",
        (4, 4),
    ),
    "weak but not branching merge": (
        """\
des (0,10,7)
(0,"d",1)
(0,"d",2)
(1,"a",3)
(2,"a",4)
(2,"a",5)
(3,"b",6)
(3,"tau",4)
(4,"c",6)
(5,"b",6)
(5,"tau",4)
""",
        (5, 5),
    ),
    "ignored divergence": (
        """\
des (0,2,2)
(0,"a",1)
(1,"tau",1)
""",
        (2, 1),
    ),
    "mixed tau cycle": (
        """\
des (0,7,7)
(0,"tau",4)
(2,"tau",1)
(3,"tau",2)
(4,"tau",3)
(1,"tau",5)
(5,"tau",6)
(6,"a",3)
""",
        (1, 1),
    ),
    "tau-only fanout": (
        """\
des (0,6,5)
(0,"tau",1)
(0,"tau",2)
(0,"tau",3)
(0,"tau",4)
(3,"tau",3)
(4,"tau",4)
""",
        (1, 0),
    ),
    "terminal tau cycle": (
        """\
des (0,4,4)
(0,"a",1)
(1,"tau",2)
(2,"tau",3)
(3,"tau",1)
""",
        (2, 1),
    ),
    "non-inert tau": (
        """\
des (0,7,8)
(0,"b",1)
(0,"b",2)
(1,"a",3)
(1,"tau",4)
(2,"a",5)
(2,"tau",6)
(6,"a",7)
""",
        (4, 5),
    ),
    "repeated non-inert tau": (
        """\
des (0,5,5)
(0,"tau",1)
(0,"tau",3)
(1,"a",2)
(1,"tau",3)
(3,"tau",4)
""",
        (2, 2),
    ),
    "reachability after tau": (
        """\
des (0,7,6)
(0,"tau",1)
(0,"tau",2)
(1,"tau",3)
(2,"tau",4)
(2,"a",5)
(3,"c",5)
(4,"b",5)
""",
        (5, 6),
    ),
    "subtle tau loop": (
        """\
des (0,4,4)
(0,"tau",1)
(1,"tau",2)
(2,"tau",2)
(1,"a",3)
""",
        (2, 2),
    ),
    "duplicate transition": (
        """\
des (0,2,1)
(0,"a",0)
(0,"a",0)
""",
        (1, 1),
    ),
    "duplicate loops": (
        """\
des (0,3,1)
(0,"a",0)
(0,"b",0)
(0,"b",0)
""",
        (1, 2),
    ),
}


class WeakBisimulationTests(unittest.TestCase):
    def test_mcrl2_regression_cases(self) -> None:
        for name, (text, expected) in MCRL2_WEAK_BISIM_CASES.items():
            with self.subTest(name=name):
                result = weak_bisimulation_reduce(parse_aut(text))
                self.assertEqual(
                    (result.num_states, len(result.transitions)), expected
                )


class PipelineTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def reference_dot(self, path: Path) -> LTS:
        text = path.read_text(encoding="utf-8")
        initial_match = re.search(r"S(\d+)\s*\[\s*peripheries=2", text)
        if initial_match is None:
            self.fail(f"no initial state in {path}")
        transitions = [
            (int(source), label, int(target))
            for source, target, label in re.findall(
                r'S(\d+)\s*->\s*S(\d+)\s*\[label="([^"]*)"\]', text
            )
        ]
        states = [
            int(state)
            for state in re.findall(r"(?m)^S(\d+)(?:\s|\[|$)", text)
        ]
        return LTS.create(
            int(initial_match.group(1)),
            max(states) + 1,
            transitions,
        )

    def generate(self, sample: str, model: str) -> LTS:
        directory = self.ROOT / "samples" / sample
        count, transitions = cast_state_space(directory / model)
        observable = read_observable_actions(
            directory / "observable_actions.txt"
        )
        cast = LTS.create(
            0,
            count,
            hide_non_observable_actions(transitions, observable),
        )
        return _internal_pipeline(cast, "weak-trace")

    def test_sample_sizes(self) -> None:
        cases = [
            ("1", "heater-v1.statespace", (6, 8)),
            ("2", "heater-v1.statespace", (16, 18)),
            ("3", "watertank-v1.statespace", (38, 89)),
        ]
        for sample, model, expected in cases:
            with self.subTest(sample=sample):
                result = self.generate(sample, model)
                self.assertEqual(
                    (result.num_states, len(result.transitions)), expected
                )

    def test_samples_one_and_two_match_reference_graphs(self) -> None:
        for sample in ("1", "2"):
            with self.subTest(sample=sample):
                generated = self.generate(sample, "heater-v1.statespace")
                reference = self.reference_dot(
                    self.ROOT / "samples" / sample / "tinytwin.dot"
                )
                self.assertEqual(
                    format_aut(generated),
                    format_aut(weak_trace_reduce(reference)),
                )

    def test_sample_three_models_have_the_same_weak_traces(self) -> None:
        version_one = self.generate("3", "watertank-v1.statespace")
        version_two = self.generate("3", "watertank-v2.statespace")
        self.assertEqual(format_aut(version_one), format_aut(version_two))

    def test_time_paths_are_accumulated(self) -> None:
        source = parse_aut(
            """\
des (0,4,4)
(0,"a",1)
(1,"time +=2",2)
(2,"time +=3",3)
(3,"b",0)
"""
        )
        result = accumulate_time(source)
        self.assertIn((1, "time +=5", 3), result.transitions)
        self.assertNotIn((1, "time +=2", 2), result.transitions)
        self.assertNotIn((2, "time +=3", 3), result.transitions)

    def test_aut_round_trip(self) -> None:
        source = LTS.create(0, 2, [(0, 'a["x\\\\y"]', 1)])
        self.assertEqual(parse_aut(format_aut(source)), source)


if __name__ == "__main__":
    unittest.main()
