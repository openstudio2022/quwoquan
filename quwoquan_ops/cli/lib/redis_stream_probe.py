"""Read-only Redis stream visibility probe for local bootstrap orchestration.

Policy owner bootstrap 必须验证 authoritative 策略（Postgres）对应的
``ExperimentPolicyActivated`` 事实在下游消费的 Redis stream 中仍然可见：
事实流带 7 天 retention（XTRIM MINID + key EXPIRE），而策略存储永续，
reused 激活不发布新事件，跨轮长驻的 gamma 卷会出现「策略在、事实流空」。

这是一个只读探针：仅实现 XRANGE，绝不写入、修剪或 ACK。事实的重新发布
只允许经 product-ops 公开 command（等值 rollout）完成，禁止直写 Redis。
标准库 RESP 实现是刻意选择——ops CLI 不引入 redis 客户端依赖，探针的
命令面被钉死在只读子集上。
"""

from __future__ import annotations

import socket


class RedisStreamProbeError(RuntimeError):
    """The read-only stream probe could not produce an answer."""


def stream_field_values(
    *,
    host: str,
    port: int,
    stream: str,
    field: str,
    timeout_seconds: float = 5.0,
) -> tuple[str, ...]:
    """Return the values of ``field`` across all retained stream entries.

    缺失的 key（流从未存在或已整体过期）返回空 tuple，与空流同义：
    bootstrap 只关心「事实是否对下游可见」。
    """

    reply = _execute(
        host=host,
        port=port,
        timeout_seconds=timeout_seconds,
        command=("XRANGE", stream, "-", "+"),
    )
    if reply is None:
        return ()
    if not isinstance(reply, list):
        raise RedisStreamProbeError("XRANGE reply shape is invalid")
    values: list[str] = []
    for entry in reply:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not isinstance(entry[1], list)
        ):
            raise RedisStreamProbeError("XRANGE entry shape is invalid")
        fields = entry[1]
        for index in range(0, len(fields) - 1, 2):
            name = fields[index]
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            if name != field:
                continue
            value = fields[index + 1]
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            values.append(str(value))
    return tuple(values)


def _execute(
    *,
    host: str,
    port: int,
    timeout_seconds: float,
    command: tuple[str, ...],
) -> object:
    encoded = b"*" + str(len(command)).encode("ascii") + b"\r\n"
    for part in command:
        payload = part.encode("utf-8")
        encoded += b"$" + str(len(payload)).encode("ascii") + b"\r\n"
        encoded += payload + b"\r\n"
    try:
        with socket.create_connection(
            (host, port), timeout=max(0.1, timeout_seconds)
        ) as connection:
            connection.sendall(encoded)
            reader = connection.makefile("rb")
            try:
                return _read_reply(reader)
            finally:
                reader.close()
    except OSError as exc:
        raise RedisStreamProbeError(
            f"redis stream probe transport failed: {type(exc).__name__}"
        ) from exc


def _read_reply(reader) -> object:
    line = reader.readline()
    if not line.endswith(b"\r\n"):
        raise RedisStreamProbeError("redis reply is truncated")
    marker, body = line[:1], line[1:-2]
    if marker == b"+":
        return body.decode("utf-8", errors="replace")
    if marker == b"-":
        raise RedisStreamProbeError(
            "redis error reply: " + body.decode("utf-8", errors="replace")
        )
    if marker == b":":
        return int(body)
    if marker == b"$":
        length = int(body)
        if length == -1:
            return None
        payload = reader.read(length + 2)
        if len(payload) != length + 2 or not payload.endswith(b"\r\n"):
            raise RedisStreamProbeError("redis bulk reply is truncated")
        return payload[:-2]
    if marker == b"*":
        count = int(body)
        if count == -1:
            return None
        return [_read_reply(reader) for _ in range(count)]
    raise RedisStreamProbeError("redis reply marker is unsupported")
