#!/bin/bash

find . -maxdepth 1 -type d -exec sh -c 'echo -n "{}: "; find "{}" -type f | wc -l' \; | sort -t ':' -k 2n
