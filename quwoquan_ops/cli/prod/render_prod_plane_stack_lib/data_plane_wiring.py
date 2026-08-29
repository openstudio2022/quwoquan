"""prod plane 数据面接线：把服务的存储 scene 接到本平面的实例上。"""

from __future__ import annotations

from typing import Any


def _wire_redis_scene(
    environment: dict[str, Any],
    key_root: str,
    addr: str,
) -> None:
    """把一个 Redis scene 接到 prod plane 的明文单点 Redis 上。

    地址、物理组网与传输安全必须成套注入，因此它们只有这一个写入口。环境快照
    描述的是云上 prod 的组网（多数 scene 声明 `mode: cluster` / `tls: true`），
    而本平面只有一个明文单点实例；只注入地址而漏掉组网降档会让单点地址被当成
    集群种子——`addrs` 为空，servicekit 在装配期直接判否，服务起不来；漏掉 TLS
    降档则是按 TLS 握手连明文端口，只表现为依赖超时而不是配置错误。
    """
    environment[f"{key_root}_ADDR"] = addr
    environment[f"{key_root}_MODE"] = "standalone"
    environment[f"{key_root}_TLS"] = "false"
