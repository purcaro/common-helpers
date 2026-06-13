#!/bin/bash

# Usage: count_files.sh [dir ...]
# Count files recursively in each subdirectory of the given dirs (default: current dir).

dirs=("${@:-.}")

for base in "${dirs[@]}"; do
    find "$base" -maxdepth 1 -type d -exec sh -c 'echo -n "{}: "; find "{}" -type f | wc -l' \; | sort -t ':' -k 2n
done
