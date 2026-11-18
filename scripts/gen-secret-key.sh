#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<USAGE
Usage: $(basename "$0") [-h] [LENGTH]

Generate a Django SECRET_KEY safe to paste into a .env file that docker
compose reads. Prints the key on stdout; copy it in yourself.

Compose interpolates variables in .env values, so a key containing \$name
is silently replaced with an empty string and Django ends up running with
a different key than the file shows. Characters that break .env parsing or
shell handling are excluded too:

  \$        compose variable interpolation
  #        starts a comment in unquoted .env values
  " ' \\ \`   quoting and escaping

LENGTH defaults to 50, matching Django's own generator.

Options:
  -h, --help    Show this help message and exit
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

LENGTH="${1:-50}"

if [[ ! "$LENGTH" =~ ^[0-9]+$ ]] || [[ "$LENGTH" -lt 32 ]]; then
    echo "LENGTH must be an integer >= 32 (got: $LENGTH)" >&2
    exit 1
fi

python3 - "$LENGTH" <<'PY'
import secrets
import string
import sys

# Letters and digits plus punctuation that survives .env parsing, compose
# interpolation and a trip through a shell.
ALPHABET = string.ascii_letters + string.digits + "!%&*+,-./:;<=>?@^_|~"

length = int(sys.argv[1])
print("".join(secrets.choice(ALPHABET) for _ in range(length)))
PY
