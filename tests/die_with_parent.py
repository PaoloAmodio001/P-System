"""Run a process of the tests so that it dies when the process that started it dies.

Nothing in pytest can run after a SIGKILL of pytest, so the child has to notice by itself. It looks at
its parent from a thread. PR_SET_PDEATHSIG would be shorter, but it fires when the thread that started the
child ends, and tests do start nodes from threads. The product knows nothing of this: the same code runs in
the same process, with the same signals and the same exit codes.

    subprocess.Popen(command("-m", "network.cli", "node", "--config", path))
    subprocess.Popen(command(worker.__file__, mode, path))
"""

import os
import runpy
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLL_SECONDS = 0.2


def command(*target: str) -> list[str]:
    return [sys.executable, __file__, str(os.getpid()), *target]


def _watch(parent: int) -> None:
    while os.getppid() == parent:
        time.sleep(POLL_SECONDS)

    os.kill(os.getpid(), signal.SIGKILL)


def main() -> None:
    # The parent is given and not read here: it may already be dead by now.
    parent, *target = sys.argv[1:]
    threading.Thread(target=_watch, args=(int(parent),), daemon=True).start()
    # Python put the directory of this file first, and a module named like one of the tests would win.
    sys.path[0] = str(ROOT)

    if target[0] == "-m":
        sys.argv = target[1:]
        runpy.run_module(target[1], run_name="__main__", alter_sys=True)
    else:
        sys.argv = target
        sys.path.insert(0, str(Path(target[0]).resolve().parent))
        runpy.run_path(target[0], run_name="__main__")


if __name__ == "__main__":
    main()
