#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"

echo "正在查找可用的 iOS 模拟器..."

DEVICE_ROWS=()
while IFS= read -r line; do
    [ -n "$line" ] && DEVICE_ROWS+=("$line")
done < <(python3 - <<'PY'
import json
import subprocess
data = json.loads(
    subprocess.check_output(
        ["xcrun", "simctl", "list", "devices", "available", "-j"],
        text=True,
    )
)

def format_runtime(runtime_key: str) -> str:
    marker = "SimRuntime."
    if marker in runtime_key:
        runtime_key = runtime_key.split(marker, 1)[1]
    runtime_key = runtime_key.replace("iOS-", "iOS ")
    runtime_key = runtime_key.replace("-", ".")
    return runtime_key

devices = []
for runtime_key, runtime_devices in data.get("devices", {}).items():
    for device in runtime_devices:
        if device.get("isAvailable") and "iphone" in device.get("name", "").lower():
            devices.append(
                (
                    device["name"],
                    device["udid"],
                    device.get("state", "Shutdown"),
                    format_runtime(runtime_key),
                )
            )

devices.sort(key=lambda item: (item[2] != "Booted", item[0], item[3], item[1]))
for row in devices:
    print("\t".join(row))
PY
)

if [ "${#DEVICE_ROWS[@]}" -eq 0 ]; then
    echo "错误: 未找到可用的 iOS 模拟器"
    echo "请先安装或创建一个 iPhone 模拟器"
    exit 1
fi

if [ "$#" -gt 0 ]; then
    echo "提示: 已忽略传入参数；当前脚本在检测到多个设备时会要求人工选择。"
fi

if [ "${#DEVICE_ROWS[@]}" -eq 1 ]; then
    IFS=$'\t' read -r DEVICE_NAME DEVICE_ID DEVICE_STATE DEVICE_RUNTIME <<< "${DEVICE_ROWS[0]}"
    echo "仅检测到一个可用设备，自动选择: $DEVICE_NAME [$DEVICE_RUNTIME] ($DEVICE_ID)"
else
    echo "检测到多个可用的 iPhone 模拟器，请手动选择："
    for index in "${!DEVICE_ROWS[@]}"; do
        IFS=$'\t' read -r DEVICE_NAME DEVICE_ID DEVICE_STATE DEVICE_RUNTIME <<< "${DEVICE_ROWS[$index]}"
        printf '%d. %s [%s] - %s (%s)\n' \
            "$((index + 1))" \
            "$DEVICE_NAME" \
            "$DEVICE_STATE" \
            "$DEVICE_RUNTIME" \
            "$DEVICE_ID"
    done

    while true; do
        read -r -p "请选择设备编号（输入 q 退出）: " CHOICE
        if [ "$CHOICE" = "q" ] || [ "$CHOICE" = "Q" ]; then
            echo "已取消。"
            exit 0
        fi
        if [[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#DEVICE_ROWS[@]}" ]; then
            IFS=$'\t' read -r DEVICE_NAME DEVICE_ID DEVICE_STATE DEVICE_RUNTIME <<< "${DEVICE_ROWS[$((CHOICE - 1))]}"
            break
        fi
        echo "输入无效，请重新输入。"
    done
fi

echo "找到设备: $DEVICE_NAME [$DEVICE_RUNTIME] ($DEVICE_ID)"

if [ "$DEVICE_STATE" != "Booted" ]; then
    echo "正在启动模拟器..."
    xcrun simctl boot "$DEVICE_ID" >/dev/null 2>&1 || true
    open -a Simulator >/dev/null 2>&1 || true
fi

echo "正在运行 alpha HTTPS mock stack..."
bash "$ROOT_DIR/quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh" up

echo "正在通过 env-package-backed alpha 入口启动 Flutter 应用..."
exec bash "$APP_DIR/run.sh" -d "$DEVICE_ID"
