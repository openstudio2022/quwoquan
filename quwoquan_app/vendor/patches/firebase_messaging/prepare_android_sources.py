#!/usr/bin/env python3
"""Build a pinned, warning-clean firebase_messaging Android source overlay.

The pub package remains the Dart/iOS/web truth. Android compilation consumes a
copy under build/ with only the obsolete FlutterShellArgs transport removed.
The script never edits the pub cache and fails closed when upstream source no
longer matches the expected API shape.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def _replace_once(text: str, old: str, new: str, *, source: Path) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"firebase_messaging overlay expected one match in {source}, found {count}"
        )
    return text.replace(old, new)


def _patch_executor(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        "import io.flutter.embedding.engine.FlutterShellArgs;\n",
        "",
        source=path,
    )
    text = _replace_once(text, "import java.util.Arrays;\n", "", source=path)
    text = _replace_once(
        text,
        "startBackgroundIsolate(callbackHandle, null);",
        "startBackgroundIsolate(callbackHandle);",
        source=path,
    )
    text = _replace_once(
        text,
        "public void startBackgroundIsolate(long callbackHandle, FlutterShellArgs shellArgs)",
        "public void startBackgroundIsolate(long callbackHandle)",
        source=path,
    )
    old_engine = """                  if (shellArgs != null) {
                    Log.i(
                        TAG,
                        \"Creating background FlutterEngine instance, with args: \"
                            + Arrays.toString(shellArgs.toArray()));
                    backgroundFlutterEngine =
                        new FlutterEngine(
                            ContextHolder.getApplicationContext(), shellArgs.toArray());
                  } else {
                    Log.i(TAG, \"Creating background FlutterEngine instance.\");
                    backgroundFlutterEngine =
                        new FlutterEngine(ContextHolder.getApplicationContext());
                  }
"""
    new_engine = """                  Log.i(TAG, \"Creating background FlutterEngine instance.\");
                  backgroundFlutterEngine =
                      new FlutterEngine(ContextHolder.getApplicationContext());
"""
    text = _replace_once(text, old_engine, new_engine, source=path)
    path.write_text(text, encoding="utf-8")


def _patch_service(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        "import io.flutter.embedding.engine.FlutterShellArgs;\n",
        "",
        source=path,
    )
    text = _replace_once(
        text,
        "public static void startBackgroundIsolate(long callbackHandle, FlutterShellArgs shellArgs)",
        "public static void startBackgroundIsolate(long callbackHandle)",
        source=path,
    )
    text = _replace_once(
        text,
        "flutterBackgroundExecutor.startBackgroundIsolate(callbackHandle, shellArgs);",
        "flutterBackgroundExecutor.startBackgroundIsolate(callbackHandle);",
        source=path,
    )
    path.write_text(text, encoding="utf-8")


def _patch_plugin(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        "import io.flutter.embedding.engine.FlutterShellArgs;\n",
        "",
        source=path,
    )
    old_shell_args = """        FlutterShellArgs shellArgs = null;
        if (mainActivity != null) {
          // Supports both Flutter Activity types:
          //    io.flutter.embedding.android.FlutterFragmentActivity
          //    io.flutter.embedding.android.FlutterActivity
          // We could use `getFlutterShellArgs()` but this is only available on `FlutterActivity`.
          shellArgs = FlutterShellArgs.fromIntent(mainActivity.getIntent());
        }

"""
    text = _replace_once(text, old_shell_args, "", source=path)
    text = _replace_once(
        text,
        """        FlutterFirebaseMessagingBackgroundService.startBackgroundIsolate(
            pluginCallbackHandle, shellArgs);""",
        """        FlutterFirebaseMessagingBackgroundService.startBackgroundIsolate(
            pluginCallbackHandle);""",
        source=path,
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"firebase_messaging Android source missing: {source}")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output)
    package = output / "io/flutter/plugins/firebase/messaging"
    _patch_executor(package / "FlutterFirebaseMessagingBackgroundExecutor.java")
    _patch_service(package / "FlutterFirebaseMessagingBackgroundService.java")
    _patch_plugin(package / "FlutterFirebaseMessagingPlugin.java")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
