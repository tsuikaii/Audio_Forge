#!/bin/zsh
cd -- "${0:A:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONPATH="$PWD/src"
exec python3 -B -m audio_forge
