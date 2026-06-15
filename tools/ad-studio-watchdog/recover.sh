#!/bin/zsh
# Instantly bring the Ad Studio public URL back — e.g. right after you turn OFF a VPN.
# The watchdog does this automatically within ~1-2 min; run this to skip the wait.
#   zsh tools/ad-studio-watchdog/recover.sh
exec /bin/zsh "${0:A:h}/watchdog.sh" --force
