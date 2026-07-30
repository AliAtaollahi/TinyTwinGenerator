# TinyTwinGenerator

TinyTwinGenerator generates a tiny-twin model from a Rebeca-generated
`.statespace` file and a comma-separated list of observable actions.

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
    samples/1/observable_actions.txt
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
    samples/1/observable_actions.txt
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
    samples/1/observable_actions.txt
```

In this mode, `ltsconvert` must be available in `PATH`.

## Specify an output directory

Use `-o` or `--output`:

```bash
python tinytwin.py \
    -o output \
    samples/1/heater-v1.statespace \
    samples/1/observable_actions.txt
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
<input.statespace> <observable_actions.txt>
```

`observable_actions.txt` may contain comma-separated or line-separated action
fragments. A transition label remains observable when it contains one of those
fragments. All other transition labels are written as `tau` in the intermediate
AUT before weak-trace reduction. Writing `tau` directly also handles action
labels whose data arguments contain commas.

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
    samples/1/observable_actions.txt
```

### Sample 2

All four variants in `samples/2` reduce to the same rooted, edge-labeled graph
as `samples/2/tinytwin.dot`:

```text
16 states
18 transitions
```

Both backends normalize their output to stable breadth-first state numbers.
The checked-in reference uses another numbering and writes labels such as
`label="S0"`, so textual `cmp` against that older reference is not an
appropriate graph comparison.

### Sample 3

The observable-action file for sample three contains:

```text
open_valve,close_valve,time,(
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
