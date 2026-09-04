"""PTY support for workspace Flutter facade user-zsh contract tests."""

import os
import pty
import select
import signal
import time
from pathlib import Path


class _InteractiveLoginZsh:
    PROMPT = b"__QWQ_TEST_PROMPT__ "
    COMMAND_DONE = b"__QWQ_COMMAND_DONE__"

    def __init__(self, *, home: Path, environment: dict[str, str]) -> None:
        pid, descriptor = pty.fork()
        if pid == 0:  # pragma: no cover - child process is observed through its PTY
            child_environment = dict(environment)
            child_environment.pop("ZDOTDIR", None)
            child_environment.update(
                HOME=str(home),
                TERM="dumb",
                LC_ALL="C",
            )
            os.execve("/bin/zsh", ["/bin/zsh", "-l", "-i"], child_environment)
        self.pid = pid
        self.descriptor = descriptor
        self.startup_output = self._read_until_prompt()

    def _read_until_prompt(self) -> str:
        output = bytearray()
        deadline = time.monotonic() + 10
        while self.PROMPT not in output:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    "interactive login zsh did not reach its prompt: "
                    + output.decode("utf-8", errors="replace")
                )
            readable, _, _ = select.select([self.descriptor], [], [], remaining)
            if not readable:
                continue
            try:
                chunk = os.read(self.descriptor, 4096)
            except OSError as error:
                raise AssertionError("interactive login zsh closed early") from error
            if not chunk:
                raise AssertionError("interactive login zsh closed early")
            output.extend(chunk)
        return output.decode("utf-8", errors="replace")

    def command(self, command: str) -> str:
        token = f"{self.COMMAND_DONE.decode()}_{time.time_ns()}"
        token_line = ("\r\n" + token + "\r\n").encode("utf-8")
        wrapped = f"{command}; print -r -- {token}\n"
        os.write(self.descriptor, wrapped.encode("utf-8"))
        output = bytearray()
        deadline = time.monotonic() + 15
        while token_line not in output:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    "interactive zsh command did not finish: "
                    + output.decode("utf-8", errors="replace")
                )
            readable, _, _ = select.select([self.descriptor], [], [], remaining)
            if not readable:
                continue
            try:
                chunk = os.read(self.descriptor, 4096)
            except OSError as error:
                raise AssertionError("interactive zsh command closed early") from error
            if not chunk:
                raise AssertionError("interactive zsh command closed early")
            output.extend(chunk)
        return output.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self.descriptor < 0:
            return
        try:
            os.write(self.descriptor, b"exit\n")
        except OSError:
            pass
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            waited, _ = os.waitpid(self.pid, os.WNOHANG)
            if waited == self.pid:
                break
            time.sleep(0.02)
        else:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            kill_deadline = time.monotonic() + 0.5
            while time.monotonic() < kill_deadline:
                waited, _ = os.waitpid(self.pid, os.WNOHANG)
                if waited == self.pid:
                    break
                time.sleep(0.02)
        os.close(self.descriptor)
        self.descriptor = -1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
