# Continuous time sync installed — 2026-10-18

## Operator installation receipt

Operator reported CONTINUOUS_TIME_SYNC_INSTALLED after all phases including verify_after. Package SHA256: a64bb2d83f3a42933e291efe1c829461af75c7128af993bb03bd8629514774ad. Backup: /root/freeze-time-sync.9qom636c.

Receipt confirms DietPi NTP mode 4, time_synchronized=true, light MANUAL_OFF/OK, shower USER_OFF/DRAIN, GPIO20/21/26 HIGH. Installer issued one manual_off API request to inhibit camera activation during maintenance. No ON/SUPPLY request. Cold-boot and physical acceptance NOT_TESTED.

## Independent restricted SSH verification

Read-only maintenance status retrieved successfully after installation: light MANUAL_OFF, health OK, desired_on=false, gpio_on=false; shower weather_assisted, MANUAL_DRAIN, reason user_off. Hub, paired GPIO and Node-RED active. Node-RED PID 627 and paired GPIO PID 436 preserved. Diagnostic issued zero actuator commands and zero configuration writes.

Filtered last-3000-entry journal summary had zero matching categories; this is limited evidence, not proof of long-term fault absence. Restricted status does not independently expose NTP configuration; NTP confirmation above comes from the operator installation receipt.

## Remaining verification

Cold boot, sustained clock stability and physical acceptance remain pending. Historical shower HTTP 503 cause remains unresolved. No package upgrades, Node-RED restart-policy changes, or reboot performed. Prior prepared-only documentation describes the immutable delivered package; this receipt supersedes its installation status.

## Captured status

```json
{
  "checks": [
    {
      "check": "SHOWER_STATUS",
      "mode": "weather_assisted",
      "reason": "user_off",
      "state": "MANUAL_DRAIN"
    },
    {
      "check": "LIGHT_STATUS",
      "desired_on": false,
      "gpio_on": false,
      "health": "OK",
      "manual_remaining_seconds": 1712,
      "mode": "MANUAL_OFF",
      "reason": "restart_manual_inhibited",
      "remaining_seconds": 1712,
      "revision": 87
    },
    {
      "check": "JOURNAL_SUMMARY",
      "exit": 0,
      "matches": 0,
      "max_entries": 3000
    }
  ],
  "units": {
    "freeze-protect-maintenance-install.service": {
      "ActiveState": "inactive",
      "ExecMainStatus": "0",
      "MainPID": "0",
      "NeedDaemonReload": "no",
      "Result": "success",
      "SubState": "dead"
    },
    "freeze-protect-maintenance-prepare.service": {
      "ActiveState": "inactive",
      "ExecMainStatus": "0",
      "MainPID": "0",
      "NeedDaemonReload": "no",
      "Result": "success",
      "SubState": "dead"
    },
    "freeze-protect-pair-gpio.service": {
      "ActiveState": "active",
      "ExecMainStatus": "0",
      "MainPID": "436",
      "NeedDaemonReload": "no",
      "Result": "success",
      "SubState": "running"
    },
    "freeze-protect.service": {
      "ActiveState": "active",
      "ExecMainStatus": "0",
      "MainPID": "6367",
      "NeedDaemonReload": "no",
      "Result": "success",
      "SubState": "running"
    },
    "node-red.service": {
      "ActiveState": "active",
      "ExecMainStatus": "0",
      "MainPID": "627",
      "NeedDaemonReload": "no",
      "Result": "success",
      "SubState": "running"
    }
  },
  "configuration_writes": 0,
  "actuator_commands": 0
}
```
