# sandbox entrypoint -- code read + soft timeout + output truncation
import os
import signal
import sys
import traceback
from typing import Any

SANDBOX_TIMEOUT_S = int(os.environ.get("SANDBOX_SOFT_TIMEOUT_S", "20"))
SANDBOX_MAX_OUTPUT_CHARS = int(os.environ.get("SANDBOX_MAX_OUTPUT_CHARS", "10000"))
SANDBOX_CODE_FILE = os.environ.get("SANDBOX_CODE_FILE", "/tmp/user_code.py")

_TIMED_OUT = False


def _handle_timeout(_signum: int, _frame: Any) -> None:
    global _TIMED_OUT
    _TIMED_OUT = True
    print("[SANDBOX_TIMEOUT]", flush=True)
    os._exit(124)


def _truncate_output(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[OUTPUT_TRUNCATED]"


def main() -> None:
    signal.signal(signal.SIGALRM, _handle_timeout)  # type: ignore[attr-defined]
    signal.alarm(SANDBOX_TIMEOUT_S)  # type: ignore[attr-defined]

    if not os.path.exists(SANDBOX_CODE_FILE):
        print(f"[SANDBOX_ERROR] Code file not found: {SANDBOX_CODE_FILE}", flush=True)
        sys.exit(1)

    try:
        with open(SANDBOX_CODE_FILE, encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        print(f"[SANDBOX_ERROR] Failed to read code file: {e}", flush=True)
        sys.exit(1)

    compiled = compile(code, SANDBOX_CODE_FILE, "exec")

    ns: dict[str, Any] = {"__builtins__": __builtins__}
    try:
        exec(compiled, ns)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    finally:
        signal.alarm(0)  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
