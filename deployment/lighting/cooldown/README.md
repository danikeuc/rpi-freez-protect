# Light cooldown patch
Approved behavior: manual ON expires to OFF, camera remains inhibited for900s, then AUTO OFF.
Manual OFF duration is unchanged. Explicit AUTO cancels inhibition. Restart never reenergizes.
Status DTO is unchanged. Durable state gains cooldown_until; downgrade requires restoring both
backed-up code and matching database while controller is stopped. Do not downgrade code alone.
Trusted root@DietPi console only, loads disconnected, current light OFF and pairedDRAIN required.
Run python3 -I -B install_cooldown.py --loads-disconnected once.
On stop inspect the recorded backup; do not rerun automatically.
This patch preserves environment, gateway, settings, GPIO executors and shower code.
Package identity remains1.0.0 plus the exact two-file hashes in baseline.json; no release claimed.
