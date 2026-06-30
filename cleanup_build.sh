#!/bin/bash

set -euo pipefail

build_enabled=0
output_arg=""
positional_args=()

while [ $# -gt 0 ]; do
    case "$1" in
        --build|-b)
            build_enabled=1
            shift
            ;;
        --no-build)
            build_enabled=0
            shift
            ;;
        --output|-o)
            shift
            if [ $# -eq 0 ]; then
                echo "Error: missing output path after -o/--output."
                exit 1
            fi
            output_arg="$1"
            shift
            ;;
        --help|-h)
            echo "Usage: ./cleanup_build.sh [--build|-b] [-o <output-dir>] <input.statespace> <observable_actions.txt>"
            exit 0
            ;;
        *)
            positional_args+=("$1")
            shift
            ;;
    esac
done

if [ "${#positional_args[@]}" -lt 2 ]; then
    echo "Error: missing arguments."
    echo "Usage: ./cleanup_build.sh [--build|-b] [-o <output-dir>] <input.statespace> <observable_actions.txt>"
    exit 1
fi

if [ "${#positional_args[@]}" -gt 2 ]; then
    echo "Error: too many arguments."
    echo "Usage: ./cleanup_build.sh [--build|-b] [-o <output-dir>] <input.statespace> <observable_actions.txt>"
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
run_dir="$(pwd)"
build_dir="$script_dir/build"

if [ -z "$output_arg" ]; then
    output_dir="$run_dir"
else
    case "$output_arg" in
        /*) output_dir="$output_arg" ;;
        *)  output_dir="$run_dir/$output_arg" ;;
    esac
fi

case "${positional_args[0]}" in
    /*) statespace_file="${positional_args[0]}" ;;
    *)  statespace_file="$run_dir/${positional_args[0]}" ;;
esac

case "${positional_args[1]}" in
    /*) observable_file="${positional_args[1]}" ;;
    *)  observable_file="$run_dir/${positional_args[1]}" ;;
esac

if [ ! -f "$statespace_file" ]; then
    echo "Error: statespace file not found: $statespace_file"
    exit 1
fi

if [ ! -f "$observable_file" ]; then
    echo "Error: observable-actions file not found: $observable_file"
    exit 1
fi

cast_bin="$script_dir/castfunction_variables/bin/castfunction_variables"
extract_bin="$script_dir/extraction_function/bin/extraction_function"

if [ "$build_enabled" -eq 1 ]; then
    rm -rf "$script_dir/castfunction_variables/build"
    rm -rf "$script_dir/castfunction_variables/src-gen"
    rm -rf "$script_dir/castfunction_variables/bin"
    rm -rf "$script_dir/castfunction_variables/include"
    rm -rf "$script_dir/castfunction_variables/lib"
    rm -rf "$script_dir/castfunction_variables/share"

    rm -rf "$script_dir/extraction_function/build"
    rm -rf "$script_dir/extraction_function/src-gen"
    rm -rf "$script_dir/extraction_function/bin"
    rm -rf "$script_dir/extraction_function/include"
    rm -rf "$script_dir/extraction_function/lib"
    rm -rf "$script_dir/extraction_function/share"

    cd "$script_dir/castfunction_variables"
    lfc castfunction_variables.lf

    cd "$script_dir/extraction_function"
    lfc extraction_function.lf
fi

if [ ! -x "$cast_bin" ]; then
    echo "Error: castfunction_variables binary not found. Run with --build."
    exit 1
fi

if [ ! -x "$extract_bin" ]; then
    echo "Error: extraction_function binary not found. Run with --build."
    exit 1
fi

rm -rf "$build_dir"
mkdir -p "$build_dir/cast" "$build_dir/extract" "$output_dir"

config_file="$build_dir/temp.txt"
cast_file="$build_dir/cast.aut"
clean_file="$build_dir/clean.aut"
tau_file="$build_dir/tau.txt"
raw_file="$build_dir/raw.aut"
timed_file="$build_dir/timed.aut"
out_aut="$output_dir/tinytwin.aut"
out_dot="$output_dir/tinytwin.dot"

printf "%s\n" "$statespace_file" > "$config_file"

cd "$build_dir/cast"
"$cast_bin" > "$cast_file"

cd "$script_dir"

sed -i '1,2d' "$cast_file"

first_line=$(head -n 1 "$cast_file")
state_count=$(echo "$first_line" | awk -F ' ' '{print $4}')
transition_count=$(echo "$first_line" | awk -F ' ' '{print $8}')

sed -i "1s/.*/des(0,$transition_count,$state_count)/" "$cast_file"

awk '
{
    lines[NR] = $0
}
END {
    last = NR

    while (last > 0 && lines[last] ~ /^[[:space:]]*$/) {
        last--
    }

    if (last > 0) {
        sub(/[[:space:]]+$/, "", lines[last])
    }

    for (i = 1; i <= last; i++) {
        if (i > 1) {
            printf "\n"
        }
        printf "%s", lines[i]
    }
}
' "$cast_file" > "$clean_file"

printf "%s\n" "$clean_file" > "$config_file"
cat "$observable_file" >> "$config_file"

cd "$build_dir/extract"
"$extract_bin" > "$tau_file"

cd "$script_dir"

tau_actions=$(awk '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0); printf "%s", $0}' "$tau_file")
printf "%s" "$tau_actions" > "$tau_file"

ltsconvert --equivalence=weak-trace --tau="$tau_actions" "$clean_file" "$raw_file"

python3 "$script_dir/time_accumulator.py" "$raw_file" > "$timed_file"

ltsconvert --equivalence=weak-trace "$timed_file" "$out_aut"
ltsconvert "$out_aut" "$out_dot"

echo "Generated:"
echo "$out_aut"
echo "$out_dot"