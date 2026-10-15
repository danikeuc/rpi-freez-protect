# Light relay commissioning continuation

Owner authorizes connecting MCP to relay21, lamp disconnected. Confirm valve24V
also disconnected and USER_OFF before driver bench. Fresh read2026-10-15 showed
paired LOW/LOW; do not treat older DRAIN evidence as current.

1. Prepare bounded root-console GPIO21 bench package first. Use installed isolated
   gpiod2.3 interpreter. Require exact Pi4, installed paired daemon hash/ownership,
   USER_OFF, high/high readback and no existing GPIO21 owner. Read-only mmap samples
   capture levels/direction of20/21/26. Only request/write21. Exercise startup OFF,
   shortON/OFF, normal release, child crash whileON, finalOFF recovery. Retain
   samples privately; do not claim high-speed/physical validation from point samples.
2. Test guards, worker GPIO mask, cleanup and failure with fake driver/transport;
   independent review before handoff. Build pinned archive and checksum; serve from
   workstation without a30min expiry. Root-console command is required: existing
   remote helper only authorizes pinned paired migration, not this new bench.
3. Actual bench result gates service/HTTPS ingress/token provisioning. Do not create
   commissioned marker or deploy source forwarding while release safety remains
   unknown. Follow findings; failure requires assessment, not repeatedON.

The next package is a driver commissioning test, not finished automation. Full
light controller installation will follow only after the driver gate is resolved.
