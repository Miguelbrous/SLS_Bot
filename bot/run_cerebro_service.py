from __future__ import annotations

import signal
import time

from cerebro.service import Cerebro


class Runner:
    def __init__(self) -> None:
        self.cerebro = Cerebro()
        self._stopped = False

    def _handle_signal(self, signum, frame):  # type: ignore[override]
        self._stopped = True
        self.cerebro.stop_loop()

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        self.cerebro.start_loop()
        try:
            while not self._stopped:
                time.sleep(5)
        finally:
            self.cerebro.stop_loop()


def main() -> None:
    Runner().run()


if __name__ == "__main__":
    main()
