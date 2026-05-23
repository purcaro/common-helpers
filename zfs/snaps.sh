#!/bin/bash

zfs list -o space | sort -h -k 4 | awk '$4 !~ /0B/' | grep --color 'T \|G'
