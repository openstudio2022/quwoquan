#!/usr/bin/env bash
# 使用固定 VM 服务端口启动，避免代理拦截；在终端请用此脚本或带参数命令，不要直接用 flutter run。
cd "$(dirname "$0")"
exec flutter run --host-vmservice-port=8888 --dds-port=8889 "$@"
