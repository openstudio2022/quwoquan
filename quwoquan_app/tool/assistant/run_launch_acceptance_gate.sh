#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "[gate] Step 1/3: loopback health check"
python3 - <<'PY'
import socket
import threading
import time
import sys

HOST = "127.0.0.1"
PORT = 52991
received = []

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(1)

def serve():
    try:
        conn, _ = server.accept()
        data = conn.recv(64)
        if data:
            received.append(data)
            conn.sendall(b"ok")
        conn.close()
    except Exception:
        pass

thread = threading.Thread(target=serve, daemon=True)
thread.start()
time.sleep(0.15)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.settimeout(2)
try:
    client.connect((HOST, PORT))
    client.sendall(b"ping")
    _ = client.recv(16)
except Exception:
    pass
finally:
    client.close()
    time.sleep(0.2)
    server.close()

if not received:
    print(
        "[gate][fatal] loopback TCP is unavailable. "
        "Please disable network tunneling/proxy filtering (TUN/VPN/firewall), "
        "then rerun this gate."
    )
    sys.exit(12)

print("[gate] loopback is healthy")
PY

echo "[gate] Step 2/3: flutter analyze"
flutter analyze \
  lib/ui/chat/pages/chat_detail_page.dart \
  lib/assistant/api/assistant_api_gateway.dart \
  lib/assistant/application/assistant_gateway.dart \
  lib/assistant/application/assistant_providers.dart \
  lib/assistant/application/assistant_edge_service.dart \
  lib/assistant/runtime/assistant_runtime.dart \
  lib/assistant/spi/assistant_adapter_runtime.dart \
  lib/core/constants/app_concept_constants.dart \
  lib/core/constants/ui_text_constants.dart \
  test/ui/chat/widgets/chat_detail_page_assistant_ui_regression_test.dart

echo "[gate] Step 3/3: flutter tests"
flutter test test/ui/chat/widgets/chat_detail_page_assistant_ui_regression_test.dart

echo "[gate] PASS: launch acceptance gate passed"
