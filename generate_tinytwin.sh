#!/usr/bin/env bash

set -euo pipefail

usage() {
    echo "Usage: ./generate_tinytwin.sh [-o <output-dir>] <input.statespace> <observable_actions.txt>"
}

output_arg=""
positional_args=()

while [ "$#" -gt 0 ]; do
    case "$1" in
        --output|-o)
            shift
            if [ "$#" -eq 0 ]; then
                echo "Error: missing output path after -o/--output." >&2
                usage >&2
                exit 1
            fi
            output_arg="$1"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --build|-b|--no-build)
            echo "Error: $1 is no longer needed; this version has no build step." >&2
            usage >&2
            exit 1
            ;;
        -*)
            echo "Error: unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            positional_args+=("$1")
            shift
            ;;
    esac
done

if [ "${#positional_args[@]}" -ne 2 ]; then
    echo "Error: expected a state-space file and an observable-actions file." >&2
    usage >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
run_dir="$(pwd)"

case "${positional_args[0]}" in
    /*) statespace_file="${positional_args[0]}" ;;
    *) statespace_file="$run_dir/${positional_args[0]}" ;;
esac

case "${positional_args[1]}" in
    /*) observable_file="${positional_args[1]}" ;;
    *) observable_file="$run_dir/${positional_args[1]}" ;;
esac

if [ -z "$output_arg" ]; then
    output_dir="$run_dir"
else
    case "$output_arg" in
        /*) output_dir="$output_arg" ;;
        *) output_dir="$run_dir/$output_arg" ;;
    esac
fi

if [ ! -f "$statespace_file" ]; then
    echo "Error: state-space file not found: $statespace_file" >&2
    exit 1
fi

if [ ! -f "$observable_file" ]; then
    echo "Error: observable-actions file not found: $observable_file" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 was not found in PATH." >&2
    exit 1
fi

if ! command -v ltsconvert >/dev/null 2>&1; then
    echo "Error: ltsconvert was not found in PATH (install the mCRL2 toolset)." >&2
    exit 1
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/tinytwin.XXXXXXXX")"
trap 'rm -rf -- "$work_dir"' EXIT

mkdir -p "$output_dir"

cast_file="$work_dir/cast.aut"
tau_file="$work_dir/tau.txt"
raw_file="$work_dir/raw.aut"
timed_file="$work_dir/timed.aut"
out_aut="$output_dir/tinytwin.aut"
out_dot="$output_dir/tinytwin.dot"

python3 "$script_dir/cast_and_extract.py" \
    "$statespace_file" \
    "$observable_file" \
    --aut-output "$cast_file" \
    --tau-output "$tau_file"

tau_actions="$(<"$tau_file")"
ltsconvert --equivalence=weak-trace --tau="$tau_actions" \
    "$cast_file" "$raw_file"

python3 "$script_dir/time_accumulator.py" "$raw_file" > "$timed_file"

ltsconvert --equivalence=weak-trace "$timed_file" "$out_aut"
ltsconvert "$out_aut" "$out_dot"

echo "Generated:"
echo "$out_aut"
echo "$out_dot"
