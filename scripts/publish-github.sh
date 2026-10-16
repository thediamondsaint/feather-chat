#!/usr/bin/env bash
# Publish the reviewed source commit to the user's requested public repository.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
repository=thediamondsaint/feather-chat
if ! login=$(gh api user --jq .login); then
    printf '%s\n' 'GitHub is unreachable or gh is not signed in. Run gh auth login, then retry this script.' >&2
    exit 1
fi
if [[ "$login" != thediamondsaint ]]; then
    printf '%s\n' 'Please sign gh into thediamondsaint before publishing this repository.' >&2
    exit 1
fi
if gh repo view "$repository" --json isPrivate >/dev/null 2>&1; then
    if [[ $(gh repo view "$repository" --json isPrivate --jq .isPrivate) != false ]]; then
        printf '%s\n' 'The existing repository is private. Its visibility has not been changed.' >&2
        exit 1
    fi
else
    gh repo create "$repository" --public --description 'FeatherGPT: a lightweight native ChatGPT client for Omarchy and Hyprland.'
fi
if [[ $(git remote get-url origin) != https://github.com/thediamondsaint/feather-chat.git ]]; then
    printf '%s\n' 'Unexpected origin URL; nothing has been pushed.' >&2
    exit 1
fi
git push -u origin main
printf '%s\n' 'Published: https://github.com/thediamondsaint/feather-chat'
