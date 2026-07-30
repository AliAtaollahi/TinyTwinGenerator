# TinyTwinGenerator

TinyTwinGenerator generates a tiny-twin model from a Rebeca-generated
`.statespace` file and a comma-separated list of class-qualified observable
messages.

Run the complete pipeline through `tinytwin.py`. It works on Windows and Linux
and has built-in weak-trace and weak-bisimulation reductions. Lingua Franca,
C/C++, CMake, Make, shell scripts, and mCRL2 are not required.

## Requirements

- Python 3.10 or newer

mCRL2's `ltsconvert` is optional. It is used only when `--mcrl2` is supplied.
The built-in algorithms were checked against mCRL2 toolset 202407.1.

## Run

Weak trace is the default:

```bash
python tinytwin.py \
    samples/1/heater-v1.statespace \
    samples/1/observable_messages.txt
```

On Windows, `py tinytwin.py ...` can be used when the Python launcher is
installed.

The two generated files are:

```text
tinytwin.aut
tinytwin.dot
```

There is no build or compile step.

## Choose the equivalence

Use `--equivalence weak-trace` (the default) or
`--equivalence weak-bisim`:

```bash
python tinytwin.py \
    --equivalence weak-bisim \
    samples/1/heater-v1.statespace \
    samples/1/observable_messages.txt
```

The reductions are divergence-insensitive, matching mCRL2's `weak-trace` and
`weak-bisim` choices.

To explicitly use an installed mCRL2 `ltsconvert` instead of the built-in
implementation, add `--mcrl2`:

```bash
python tinytwin.py \
    --mcrl2 \
    --equivalence weak-trace \
    samples/1/heater-v1.statespace \
    samples/1/observable_messages.txt
```

In this mode, `ltsconvert` must be available in `PATH`.
The caster and time accumulator preserve their legacy transition order in this
mode, so mCRL2 emits the same state numbering and DOT edge order as the earlier
shell pipeline.

## Specify an output directory

Use `-o` or `--output`:

```bash
python tinytwin.py \
    -o output \
    samples/1/heater-v1.statespace \
    samples/1/observable_messages.txt
```

This writes:

```text
output/tinytwin.aut
output/tinytwin.dot
```

Relative paths are resolved from the directory in which the command is run.
The built-in pipeline does not create intermediate files. `--mcrl2` uses an
automatically removed temporary directory.

## Input files

The command expects:

```text
<input.statespace> <observable_messages.txt>
```

`observable_messages.txt` may contain comma-separated or line-separated
entries. Every message entry must use the exact `owner.message` form, such as
`controller.getsense`. Matching is case-insensitive and ignores data arguments.
The reserved entry `time` selects time-progress transitions.

The owner qualifier is required. Therefore, selecting `first.update` does not
also expose `second.update` when two reactive classes or rebec instances define
the same message name. Ambiguous unqualified entries such as `update` are
rejected instead of silently matching both classes.

All unselected transition labels are written as `tau` in the intermediate AUT
before reduction. Writing `tau` directly also handles action labels whose data
arguments contain commas.

### Nondeterministic values

When the state space contains multiple copies of the same action from the same
source state, the caster compares their destination states. A branch-result
value is added to each edge when the branches propagate that value through a
newly queued message.

For example, sample two contains two `room.tempchange` transitions whose
destination states propagate different temperatures:

```text
room.tempchange[20].[]
room.tempchange[21].[]
```

If exactly one state variable distinguishes the destination states, that value
can also be annotated without a queued-message argument.

## Sample verification

### Sample 1

All four state-space variants in `samples/1` reduce to the checked-in
`samples/1/tinytwin.dot` graph. State numbers may differ because state numbers
have no semantic meaning.

```bash
python tinytwin.py \
    -o output/heater-v1 \
    samples/1/heater-v1.statespace \
    samples/1/observable_messages.txt
```

### Sample 2

All four variants in `samples/2` reduce to the same rooted, edge-labeled graph
as `samples/2/tinytwin.dot`:

```text
16 states
18 transitions
```

The generated DOT uses mCRL2's state numbering and omits redundant explicit
node labels when `--mcrl2` is selected. The built-in implementation uses
stable breadth-first state numbers. The checked-in reference uses another
numbering and writes labels such as `label="S0"`, so textual `cmp` is not an
appropriate graph comparison.

### Sample 3

The observable-message file for sample three contains:

```text
v1.open_valve,v1.close_valve,v2.open_valve,v2.close_valve,v3.open_valve,v3.close_valve,time
```

The final tiny twins therefore contain only:

```text
v1.open_valve[].[]
v1.close_valve[].[]
v2.open_valve[].[]
v2.close_valve[].[]
v3.open_valve[].[]
v3.close_valve[].[]
time +=10
```

Actions with comma-containing values, such as
`sensor.senselevel[1, 1].[]`, are hidden correctly.

## Help

```bash
python tinytwin.py --help
```
