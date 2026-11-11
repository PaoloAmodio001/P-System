"""
The rules of rounds, run from the Lean model: formal/lean/PSystem/Core.lean.

`step`, `choose`, `justified` and `leader` call the compiled definitions of
formal/lean/PSystem/QuorumRounds.lean, the ones its theorems are about. This module only finds
the library, starts the Lean runtime once, and passes JSON both ways. What it passes in has
been checked here first: members are numbers below `n`, and every signer passed to Lean has a
valid signature, checked by the caller.

The library is built with `cd formal/lean && lake build PSystem:shared`. Its path can be given
with the environment variable PSYSTEM_LEAN_CORE; the Lean runtime is found with `lean
--print-prefix`, or with PSYSTEM_LEAN_PREFIX.
"""

import ctypes
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY = ROOT / "formal" / "lean" / ".lake" / "build" / "lib" / "libPSystem_PSystem.so"

# The layout of a Lean string object (lean.h): a header of 8 bytes, then size, capacity and
# length, each a size_t, then the bytes with a final zero. `size` counts that zero.
_STRING_SIZE_OFFSET = 8
_STRING_DATA_OFFSET = 32


class LeanCoreUnavailable(RuntimeError):
    """The compiled model cannot be loaded: the node cannot run rounds."""


class LeanCoreError(ValueError):
    """The model refused an argument as malformed."""


def _lean_prefix() -> Path:
    given = os.environ.get("PSYSTEM_LEAN_PREFIX")
    if given:
        return Path(given)

    lean = shutil.which("lean") or str(Path.home() / ".elan" / "bin" / "lean")
    try:
        found = subprocess.run(
            [lean, "--print-prefix"],
            cwd=ROOT / "formal" / "lean",
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LeanCoreUnavailable(f"LEAN RUNTIME NOT FOUND: {error}") from error
    return Path(found.stdout.strip())


class _Core:
    def __init__(self) -> None:
        library = Path(os.environ.get("PSYSTEM_LEAN_CORE", DEFAULT_LIBRARY))
        if not library.exists():
            raise LeanCoreUnavailable(
                f"LEAN CORE NOT BUILT: {library} (cd formal/lean && lake build PSystem:shared)"
            )

        runtime = _lean_prefix() / "lib" / "lean" / "libleanshared.so"
        try:
            self.runtime = ctypes.CDLL(str(runtime), mode=ctypes.RTLD_GLOBAL)
            self.library = ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
        except OSError as error:
            raise LeanCoreUnavailable(f"LEAN CORE NOT LOADED: {error}") from error

        self.runtime.lean_initialize_runtime_module.restype = None
        self.runtime.lean_initialize_runtime_module()
        initialize = self.library.initialize_PSystem_PSystem_Core
        initialize.restype = ctypes.c_void_p
        initialize.argtypes = [ctypes.c_uint8, ctypes.c_void_p]
        initialize(1, None)
        self.runtime.lean_io_mark_end_initialization.restype = None
        self.runtime.lean_io_mark_end_initialization()

        self.runtime.lean_mk_string.restype = ctypes.c_void_p
        self.runtime.lean_mk_string.argtypes = [ctypes.c_char_p]
        self.functions = {}
        for name in ("step", "choose", "justified", "leader"):
            function = getattr(self.library, f"psystem_rounds_{name}")
            function.restype = ctypes.c_void_p
            function.argtypes = [ctypes.c_void_p]
            self.functions[name] = function
        self.release = self.library.psystem_release
        self.release.restype = ctypes.c_uint8
        self.release.argtypes = [ctypes.c_void_p]
        # One call at a time: the runtime is shared, and calls are short.
        self.lock = threading.Lock()

    def call(self, name: str, argument: dict):
        text = json.dumps(argument, separators=(",", ":")).encode()
        if b"\0" in text:
            raise LeanCoreError("NUL IN ARGUMENT")

        with self.lock:
            # The function takes the argument and frees it; the answer is ours to give back.
            answer = self.functions[name](self.runtime.lean_mk_string(text))
            size = ctypes.c_size_t.from_address(answer + _STRING_SIZE_OFFSET).value
            raw = ctypes.string_at(answer + _STRING_DATA_OFFSET, size - 1)
            self.release(answer)

        result = json.loads(raw)
        if not result.get("ok"):
            raise LeanCoreError(result.get("error", "REFUSED"))
        return result["result"]


_core: _Core | None = None
_core_lock = threading.Lock()


def _get() -> _Core:
    global _core
    with _core_lock:
        if _core is None:
            _core = _Core()
        return _core


def step(n: int, f: int, state: dict | None, event: dict) -> dict:
    """The next state of a validator for one key: `Rounds.step`."""
    return _get().call("step", {"n": n, "f": f, "state": state, "input": event})


def choose(n: int, f: int, reports: list[dict]) -> str | None:
    """The value reports force: `Rounds.choose`."""
    return _get().call("choose", {"n": n, "f": f, "reports": reports})


def justified(n: int, f: int, round_: int, value: str, reports: list[dict]) -> bool:
    """Whether reports justify a proposal: `Rounds.justified`."""
    return _get().call("justified", {"n": n, "f": f, "round": round_, "value": value, "reports": reports})


def leader(n: int, offset: int, round_: int) -> int:
    """The leader of a round: `Rounds.leader`."""
    return _get().call("leader", {"n": n, "k": offset, "r": round_})
