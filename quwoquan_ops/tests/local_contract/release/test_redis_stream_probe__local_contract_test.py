# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001

from __future__ import annotations

import socket
import threading
import unittest

from quwoquan_ops.cli.lib.redis_stream_probe import (
    RedisStreamProbeError,
    stream_field_values,
)


def _bulk(value: bytes) -> bytes:
    return b"$" + str(len(value)).encode() + b"\r\n" + value + b"\r\n"


def _serve_once(reply: bytes) -> tuple[int, list[bytes]]:
    """Run a one-shot fake Redis server; return its port and captured requests."""

    received: list[bytes] = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def handle() -> None:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(5.0)
            received.append(connection.recv(65536))
            connection.sendall(reply)
        listener.close()

    thread = threading.Thread(target=handle, daemon=True)
    thread.start()
    return port, received


class RedisStreamProbeLocalContractTest(unittest.TestCase):
    def test_probe_issues_read_only_xrange_and_extracts_field_values(self) -> None:
        entry_one = (
            b"*2\r\n"
            + _bulk(b"1-1")
            + b"*4\r\n"
            + _bulk(b"experimentId")
            + _bulk(b"search_ranking")
            + _bulk(b"eventType")
            + _bulk(b"ExperimentPolicyActivated")
        )
        entry_two = (
            b"*2\r\n"
            + _bulk(b"2-1")
            + b"*2\r\n"
            + _bulk(b"experimentId")
            + _bulk(b"rec_model_vs_rule")
        )
        port, received = _serve_once(b"*2\r\n" + entry_one + entry_two)

        values = stream_field_values(
            host="127.0.0.1",
            port=port,
            stream="events.ops.experiment_policy_activated",
            field="experimentId",
        )

        self.assertEqual(values, ("search_ranking", "rec_model_vs_rule"))
        request = received[0]
        self.assertIn(b"XRANGE", request)
        self.assertIn(b"events.ops.experiment_policy_activated", request)
        # 只读探针只允许发出一条 XRANGE；任何写命令都不属于它的命令面。
        for forbidden in (b"XADD", b"XTRIM", b"XDEL", b"EXPIRE", b"XACK"):
            self.assertNotIn(forbidden, request)

    def test_missing_stream_key_reads_as_empty(self) -> None:
        # XRANGE 对不存在的 key 返回空数组；整体过期的事实流与空流同义。
        port, _received = _serve_once(b"*0\r\n")

        values = stream_field_values(
            host="127.0.0.1",
            port=port,
            stream="events.ops.experiment_policy_activated",
            field="experimentId",
        )

        self.assertEqual(values, ())

    def test_error_reply_raises_probe_error(self) -> None:
        port, _received = _serve_once(
            b"-LOADING Redis is loading the dataset in memory\r\n"
        )

        with self.assertRaisesRegex(RedisStreamProbeError, "LOADING"):
            stream_field_values(
                host="127.0.0.1",
                port=port,
                stream="events.ops.experiment_policy_activated",
                field="experimentId",
            )

    def test_connection_refused_raises_probe_error(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        with self.assertRaisesRegex(RedisStreamProbeError, "transport failed"):
            stream_field_values(
                host="127.0.0.1",
                port=port,
                stream="events.ops.experiment_policy_activated",
                field="experimentId",
                timeout_seconds=1.0,
            )


if __name__ == "__main__":
    unittest.main()
