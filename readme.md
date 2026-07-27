# TinyTwinGenerator

TinyTwinGenerator generates a tiny-twin model from a Rebeca-generated
`.statespace` file and a comma-separated list of observable actions.

The runtime pipeline consists of only three files:

```text
generate_tinytwin.sh
cast_and_extract.py
time_accumulator.py
```

Lingua Franca, C/C++, CMake, and Make are not used.

## Requirements

- Python 3
- mCRL2's `ltsconvert`

The sample outputs were verified with:

```text
Python 3.13.11
ltsconvert mCRL2 toolset 202407.1 (Release)
```

## Run

```bash
./generate_tinytwin.sh \
    samples/1/heater-v1.statespace \
    samples/1/observable_actions.txt
```

The two generated files are:

```text
tinytwin.aut
tinytwin.dot
```

There is no build step.

## Specify an output directory

Use `-o` or `--output`:

```bash
./generate_tinytwin.sh \
    -o output \
    samples/1/heater-v1.statespace \
    samples/1/observable_actions.txt
```

This writes:

```text
output/tinytwin.aut
output/tinytwin.dot
```

Relative input and output paths are resolved from the directory in which the
command is run. Temporary intermediate AUT files are removed automatically.

## Input files

The command expects:

```text
<input.statespace> <observable_actions.txt>
```

`observable_actions.txt` may contain comma-separated or line-separated action
fragments. A transition label remains observable when it contains one of those
fragments. All other labels are hidden before weak-trace reduction.

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
`samples/1/tinytwin.dot`. They can be verified with:

```bash
for input in samples/1/*.statespace; do
    name="$(basename "$input" .statespace)"
    ./generate_tinytwin.sh \
        -o "output/$name" \
        "$input" \
        samples/1/observable_actions.txt
    cmp "output/$name/tinytwin.dot" samples/1/tinytwin.dot
done
```

`cmp` prints nothing when a generated file is byte-for-byte identical to the
reference.

### Sample 2

All four variants in `samples/2` reduce to the same rooted, edge-labeled graph
as `samples/2/tinytwin.dot`:

```text
16 states
18 transitions
```

The generated DOT uses mCRL2's state numbering and omits redundant explicit
node labels. The checked-in reference uses different state numbers and writes
labels such as `label="S0"`, so textual `cmp` is not an appropriate graph
comparison for sample two.

## Help

```bash
./generate_tinytwin.sh --help
```
