#!/bin/zsh
# Ad Studio — host cold-boot / power resilience (Tier 2).
#
#   zsh tools/ad-studio-watchdog/harden-host.sh           # diagnose only (default)
#   zsh tools/ad-studio-watchdog/harden-host.sh --apply   # apply the SAFE power tweaks (uses sudo)
#
# The watchdog handles "the Mac is up but the Funnel dropped". This covers the other
# case: "the Mac slept / lost power / rebooted". It reports your current posture and,
# with --apply, sets the non-destructive power settings. The security-sensitive choices
# (FileVault, autologin) are LEFT TO YOU and only printed as guidance.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1

echo "=== Ad Studio host resilience ==="
echo
echo "-- FileVault --"
fv="$(fdesetup status 2>&1)"; echo "  $fv"
echo "-- Power (want: sleep 0, SleepDisabled 1, autorestart 1, womp 1) --"
pmset -g | grep -iE 'disablesleep|autorestart|womp| sleep' | sed 's/^/  /'
echo "-- Auto-login user --"
au="$(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null || true)"
echo "  ${au:-<none>}"
echo "-- Tailscale system daemon (runs before login, unlike the GUI app) --"
if [ -f /Library/LaunchDaemons/com.tailscale.tailscaled.plist ]; then
  echo "  installed: /Library/LaunchDaemons/com.tailscale.tailscaled.plist"
else
  echo "  NOT installed as a system LaunchDaemon (funnel depends on the GUI app session)"
fi
echo

if [ "$APPLY" = "1" ]; then
  echo "=== applying SAFE power tweaks (sudo) ==="
  echo "  sudo pmset -c autorestart 1   # auto-reboot after a power failure"
  sudo pmset -c autorestart 1 || true
  echo "  sudo pmset -c sleep 0         # never idle-sleep on AC"
  sudo pmset -c sleep 0 || true
  echo "  (lid-closed serving needs: sudo pmset -a disablesleep 1 — already on if SleepDisabled=1 above)"
  echo "done."
  echo
fi

cat <<'NOTE'
=== Cold-boot decision (FileVault is the gate) ===
FileVault encrypts the whole disk, so after a FULL power-off NOTHING runs — not the
backend, not tailscaled, not the Funnel — until someone enters the unlock password at
the pre-boot screen. The watchdog can only help once the Mac is unlocked & logged in.

Pick ONE:
  A) KEEP FileVault (most secure): put the Mac on a UPS, avoid full shutdowns, and accept
     that a cold boot needs ONE manual login. After any reboot, log in once; the backend
     (launchd KeepAlive), the Funnel (--bg auto-resume) and this watchdog all come back.
  B) UNATTENDED recovery: disable FileVault on this dedicated box, then enable autologin
     (System Settings > Users & Groups > Automatically log in as ...) and run --apply
     above (autorestart 1). Now a power cut auto-reboots straight back to a serving state.
     Tradeoff: the disk (incl. .env secrets / R2 keys) is no longer encrypted at rest.

Belt-and-suspenders (either choice):
  • Ensure the open-source tailscaled is the SYSTEM daemon so the Funnel doesn't depend on
    the GUI app session:  sudo tailscaled install-system-daemon   (the GUI app detects it)
  • Confirm "Launch Tailscale at login" is ON in the Tailscale menu-bar app.
NOTE
