#!/usr/bin/env bash
# 若 Android 构建报 GeneratedPluginRegistrant 相关错误，说明 Flutter 重新生成了
# Android 插件注册表。这里统一做项目补丁：
# - dev-only 插件 integration_test / patrol 改为可选反射注册，避免进入 release 编译链。
# - startup-deferred 高 risk 插件从 eager 注册剥离，改由 StartupDeferredPluginRegistry 按需注册。
# 在项目根目录执行：./scripts/patch_android_plugin_registrant.sh

set -e
REGISTRANT="android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java"
cd "$(dirname "$0")/.."
if [ ! -f "$REGISTRANT" ]; then
  echo "Not found: $REGISTRANT"
  exit 1
fi
python3 - <<'PY'
import re
from pathlib import Path

path = Path("android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java")
text = path.read_text(encoding="utf-8")

text = text.replace(
    ".CurrentSharedPreferencesPlugin()",
    ".SharedPreferencesPlugin()",
)
text = text.replace(
    "sharedpreferences.CurrentSharedPreferencesPlugin",
    "sharedpreferences.SharedPreferencesPlugin",
)

if "io.flutter.embedding.engine.plugins.FlutterPlugin;" not in text:
    text = text.replace(
        "import io.flutter.embedding.engine.FlutterEngine;\n",
        "import io.flutter.embedding.engine.FlutterEngine;\n"
        "import io.flutter.embedding.engine.plugins.FlutterPlugin;\n",
    )

optional_dev_plugins = {
    "integration_test": "dev.flutter.plugins.integration_test.IntegrationTestPlugin",
    "patrol": "pl.leancode.patrol.PatrolPlugin",
}

startup_deferred_plugin_classes = (
    "com.ryanheise.audio_session.AudioSessionPlugin",
    "com.mr.flutter.plugin.filepicker.FilePickerPlugin",
    "co.quis.flutter_contacts.FlutterContactsPlugin",
    "com.ryanheise.just_audio.JustAudioPlugin",
    "dev.steenbakker.mobile_scanner.MobileScannerPlugin",
    "com.baseflow.permissionhandler.PermissionHandlerPlugin",
    "com.llfbandit.record.RecordPlugin",
    "dev.fluttercommunity.plus.share.SharePlusPlugin",
    "io.flutter.plugins.urllauncher.UrlLauncherPlugin",
    "io.flutter.plugins.videoplayer.VideoPlayerPlugin",
    "dev.fluttercommunity.plus.wakelock.WakelockPlusPlugin",
    "io.flutter.plugins.webviewflutter.WebViewFlutterPlugin",
    "dev.fluttercommunity.plus.connectivity.ConnectivityPlugin",
    "dev.fluttercommunity.plus.device_info.DeviceInfoPlusPlugin",
    "dev.fluttercommunity.plus.packageinfo.PackageInfoPlugin",
    "com.it_nomads.fluttersecurestorage.FlutterSecureStoragePlugin",
    "io.flutter.plugins.sharedpreferences.SharedPreferencesPlugin",
    "com.tekartik.sqflite.SqflitePlugin",
    "com.hiennv.flutter_callkit_incoming.FlutterCallkitIncomingPlugin",
    "com.cloudwebrtc.webrtc.FlutterWebRTCPlugin",
    "com.baseflow.geolocator.GeolocatorPlugin",
    "io.livekit.plugin.LiveKitPlugin",
    "io.flutter.plugins.camerax.CameraAndroidCameraxPlugin",
    "io.flutter.plugins.imagepicker.ImagePickerPlugin",
    "com.fluttercandies.photo_manager.PhotoManagerPlugin",
    "xyz.justsoft.video_thumbnail.VideoThumbnailPlugin",
)


def strip_try_catch_plugin_block(source: str, class_name: str) -> str:
    needle = f"flutterEngine.getPlugins().add(new {class_name}());"
    if needle not in source:
        return source
    block_start = source.index(needle)
    try_start = source.rfind("    try {", 0, block_start)
    if try_start < 0:
        raise SystemExit(f"Failed to locate try block for deferred plugin: {class_name}")
    catch_end = source.index("    }\n", block_start) + len("    }\n")
    return source[:try_start] + source[catch_end:]


for plugin_name, class_name in optional_dev_plugins.items():
    direct_block = (
        "    try {\n"
        f"      flutterEngine.getPlugins().add(new {class_name}());\n"
        "    } catch (Exception e) {\n"
        f"      Log.e(TAG, \"Error registering plugin {plugin_name}, {class_name}\", e);\n"
        "    }\n"
    )
    reflective_call = (
        "    registerOptionalDevPlugin(\n"
        "        flutterEngine,\n"
        f"        \"{plugin_name}\",\n"
        f"        \"{class_name}\");\n"
    )
    text = text.replace(direct_block, reflective_call)

if "private static void registerOptionalDevPlugin" not in text:
    helper = """

  private static void registerOptionalDevPlugin(
      @NonNull FlutterEngine flutterEngine,
      @NonNull String pluginName,
      @NonNull String className) {
    try {
      Class<?> pluginClass = Class.forName(className);
      Object plugin = pluginClass.getDeclaredConstructor().newInstance();
      if (plugin instanceof FlutterPlugin) {
        flutterEngine.getPlugins().add((FlutterPlugin) plugin);
      } else {
        Log.e(TAG, "Optional dev plugin " + pluginName + " does not implement FlutterPlugin: " + className);
      }
    } catch (ClassNotFoundException | NoClassDefFoundError e) {
      Log.v(TAG, "Optional dev plugin not present for this build variant: " + pluginName);
    } catch (Exception e) {
      Log.e(TAG, "Error registering optional dev plugin " + pluginName + ", " + className, e);
    }
  }
"""
    text = text.rstrip()
    if not text.endswith("}"):
        raise SystemExit("GeneratedPluginRegistrant.java has unexpected class ending")
    text = text[:-1] + helper + "}\n"

for forbidden in optional_dev_plugins.values():
    if f"new {forbidden}()" in text:
        raise SystemExit(f"Failed to patch dev-only plugin reference: {forbidden}")

for class_name in startup_deferred_plugin_classes:
    while f"new {class_name}()" in text:
        text = strip_try_catch_plugin_block(text, class_name)

for class_name in startup_deferred_plugin_classes:
    if f"new {class_name}()" in text:
        raise SystemExit(f"Failed to strip startup-deferred plugin: {class_name}")

orphan_catch = re.compile(
    r"^\s*Log\.e\(TAG, \"Error registering plugin [^\"]+\", [^)]+\), e\);\n"
    r"^\s*\}\n",
    re.MULTILINE,
)
text = orphan_catch.sub("", text)

path.write_text(text, encoding="utf-8")
PY
echo "Patched: $REGISTRANT"
