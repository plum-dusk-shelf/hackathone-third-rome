import unittest
from pathlib import Path

from server.dap_client import DapError
from server.java_debug_session import JavaDebugSession


class FakeDap:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def request(self, command, arguments):
        self.calls.append((command, arguments))
        if self.error:
            raise self.error
        return {}


class FakeStdin:
    def __init__(self):
        self.data = bytearray()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        return None


class FakeProcess:
    returncode = None

    def __init__(self):
        self.stdin = FakeStdin()


class JavaDebugSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.messages = []

        async def emit(message):
            self.messages.append(message)

        self.session = JavaDebugSession(emit, Path.cwd(), None)
        self.session.dap = FakeDap()
        self.session.thread_id = 1

    async def test_step_is_rejected_while_program_is_running(self):
        await self.session.handle({"cmd": "next"})

        self.assertEqual(self.session.dap.calls, [])
        self.assertEqual(self.messages[-1]["type"], "commandRejected")
        self.assertFalse(self.messages[-1]["paused"])

    async def test_step_resumes_only_a_suspended_thread(self):
        self.session.is_stopped = True

        await self.session.handle({"cmd": "next"})

        self.assertEqual(self.session.dap.calls, [("next", {"threadId": 1})])
        self.assertFalse(self.session.is_stopped)

    async def test_not_suspended_adapter_error_resynchronizes_debugger_state(self):
        self.session.is_stopped = True
        self.session.dap = FakeDap(DapError(
            "Failed to step because the thread 'main' is not suspended in the target VM."
        ))

        await self.session.handle({"cmd": "next"})

        self.assertFalse(self.session.is_stopped)
        self.assertEqual(self.messages[-1]["type"], "commandRejected")
        self.assertFalse(self.messages[-1]["paused"])

    async def test_input_is_acknowledged_and_written_to_java_stdin(self):
        process = FakeProcess()
        self.session.program = process

        await self.session.handle({"cmd": "input", "text": "0\n"})

        self.assertEqual(process.stdin.data, b"0\n")
        self.assertEqual(self.messages[-1]["type"], "inputAccepted")


if __name__ == "__main__":
    unittest.main()
