# common-helpers bash shortcuts
#
# Add to ~/.bashrc:
#   source /home/mjp/common-helpers/bash-shortcuts.sh

_COMMON_HELPERS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Editor
export EDITOR='emacs -nw'

# Prompt (username blinks red when root)
_set_prompt() {
    if [ "$EUID" -eq 0 ]; then
        PS1='\[\033[01;31;5m\]\u\[\033[00m\]\[\033[01;32m\]@\h\[\033[01;34m\] \w \$\[\033[00m\] '
    else
        PS1='\[\033[01;33m\]\u\[\033[00m\]\[\033[01;32m\]@\h\[\033[01;34m\] \w \$\[\033[00m\] '
    fi
}
_set_prompt
_set_title() {
    echo -ne "\033]0;${USER}@${HOSTNAME%%.*}:${PWD/$HOME/~}\007"
}
PROMPT_COMMAND='_set_prompt; _set_title'

# History
export HISTSIZE=50000

# PATH
export PATH=/home/mjp/bin:/home/mjp/.local/bin:${_COMMON_HELPERS}:$PATH

# Aliases
alias dum='du -hc --max-depth=1'
alias   g='grep -ri '
alias   e='emacs -nw -q'
alias grep='grep --color'
alias  ls='ls --color'
alias   l='ls -lh'
alias  ll='ls -lha'
alias  la='ls -A'
alias   t='tree --charset=ASCI'
alias  gg="${_COMMON_HELPERS}/commit.py"
alias   a="source '${_COMMON_HELPERS}/bash-shortcuts.sh'"
alias qmv='qmv --format=destination-only'
alias dlmp3='yt-dlp -x --extract-audio --audio-format mp3'
alias   c="${_COMMON_HELPERS}/count_files.sh"
alias   d='du -hc -d 1 | sort -h'

# make clean (separate from c=count_files.sh)
alias mc='make clean'
