import sys
import datetime
from typing import Any

class Logger:
    def __init__(self, prefix: str = "MomentumOne"):
        self.prefix = prefix

    def _fmt(self, level: str, color: str, *args: Any) -> str:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = " ".join(str(a) for a in args)
        return f"\033[90m{now}\033[0m \033[{color}m{level:<5}\033[0m: {msg}"

    def info(self, *args: Any) -> None:
        print(self._fmt("INFO", "32", *args))

    def debug(self, *args: Any) -> None:
        print(self._fmt("DEBUG", "34", *args))

    def warn(self, *args: Any) -> None:
        print(self._fmt("WARN", "33", *args), file=sys.stderr)

    def error(self, *args: Any) -> None:
        print(self._fmt("ERROR", "31", *args), file=sys.stderr)

logger = Logger()
