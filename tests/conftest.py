from datetime import UTC, datetime

from freeze_protect.lighting.executor import Receipt


class Clock:
    def __init__(self):
        self.wall = 1791850000.0
        self.mono = 100.0

    def time(self):
        return self.wall

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds

    def stamp(self):
        return datetime.fromtimestamp(self.wall, UTC).isoformat()


class Output:
    def __init__(self):
        self.on = False
        self.calls = []
        self.fail = False
        self.generation = "executor-boot"
        self.lease = None

    def off(self):
        self.calls.append("off")
        self.on = False
        self.lease = None
        if self.fail:
            raise OSError("receipt lost")
        return Receipt(
            protocol_version=1,
            request_id="off",
            command="OFF",
            gpio21=False,
            generation=self.generation,
            lease_id=None,
        )

    def begin(self):
        self.calls.append("begin")
        self.on = True
        self.lease = "lease"
        if self.fail:
            raise OSError("receipt lost")
        return Receipt(
            protocol_version=1,
            request_id="begin",
            command="ON",
            gpio21=True,
            generation=self.generation,
            lease_id=self.lease,
        )

    def renew(self):
        self.calls.append("renew")
        if self.fail:
            raise OSError("receipt lost")
        return Receipt(
            protocol_version=1,
            request_id="renew",
            command="ON",
            gpio21=self.on,
            generation=self.generation,
            lease_id=self.lease,
        )
