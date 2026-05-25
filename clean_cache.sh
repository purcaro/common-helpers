#!/bin/bash

# Remove browser and pip cache files. Close browsers first for best results.

set -u

warn_running() {
    local procs=()
    pgrep -x chrome &>/dev/null && procs+=("chrome")
    pgrep -x chromium &>/dev/null && procs+=("chromium")
    pgrep -x chromium-browser &>/dev/null && procs+=("chromium-browser")
    pgrep -x firefox &>/dev/null && procs+=("firefox")
    if ((${#procs[@]})); then
        echo "[warn] still running: ${procs[*]} (cache may not fully clear)"
    fi
}

dir_size() {
    du -sh "$1" 2>/dev/null | cut -f1
}

clean_dir() {
    local label="$1"
    local dir="$2"

    if [[ ! -d "$dir" ]]; then
        echo "[skip] $label: not found ($dir)"
        return 0
    fi

    local size
    size="$(dir_size "$dir")"
    echo "[clean] $label ($size): $dir"
    rm -rf "${dir:?}"/*
}

clean_pip_cache() {
    if command -v pip &>/dev/null; then
        echo "[clean] pip cache:"
        pip cache purge
        return 0
    fi

    if command -v pip3 &>/dev/null; then
        echo "[clean] pip3 cache:"
        pip3 cache purge
        return 0
    fi

    local pip_cache="${XDG_CACHE_HOME:-$HOME/.cache}/pip"
    if [[ -d "$pip_cache" ]]; then
        local size
        size="$(dir_size "$pip_cache")"
        echo "[clean] pip ($size): $pip_cache"
        rm -rf "${pip_cache:?}"/*
    else
        echo "[skip] pip: not found"
    fi
}

warn_running

clean_dir "chrome" "${XDG_CACHE_HOME:-$HOME/.cache}/google-chrome"
clean_dir "chromium" "${XDG_CACHE_HOME:-$HOME/.cache}/chromium"
clean_dir "firefox" "${XDG_CACHE_HOME:-$HOME/.cache}/mozilla/firefox"

clean_pip_cache

echo "[done] cache cleanup finished"
