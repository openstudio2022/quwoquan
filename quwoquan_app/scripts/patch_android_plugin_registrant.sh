#!/usr/bin/env bash
# 若 Android 构建报错「找不到符号 SharedPreferencesPlugin」，
# 说明 GeneratedPluginRegistrant 被重新生成，需改用 Java 的 LegacySharedPreferencesPlugin。
# 在项目根目录执行：./scripts/patch_android_plugin_registrant.sh

set -e
REGISTRANT="android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java"
cd "$(dirname "$0")/.."
if [ ! -f "$REGISTRANT" ]; then
  echo "Not found: $REGISTRANT"
  exit 1
fi
if grep -q "LegacySharedPreferencesPlugin" "$REGISTRANT"; then
  echo "Already patched: $REGISTRANT"
  exit 0
fi
sed -i.bak 's/\.SharedPreferencesPlugin()/.LegacySharedPreferencesPlugin()/g; s/sharedpreferences\.SharedPreferencesPlugin/sharedpreferences.LegacySharedPreferencesPlugin/g' "$REGISTRANT" && rm -f "${REGISTRANT}.bak"
echo "Patched: $REGISTRANT"
