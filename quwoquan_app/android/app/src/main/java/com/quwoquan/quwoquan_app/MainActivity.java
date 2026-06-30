package com.quwoquan.quwoquan_app;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import androidx.annotation.NonNull;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

public class MainActivity extends FlutterFragmentActivity {
  private static final String STARTUP_TAG = "QWQStartup";
  private static final String WECHAT_PACKAGE = "com.tencent.mm";
  private static final String WECHAT_FRIEND_ACTIVITY = "com.tencent.mm.ui.tools.ShareImgUI";
  private static final String WECHAT_MOMENTS_ACTIVITY =
      "com.tencent.mm.ui.tools.ShareToTimeLineUI";
  private static final long processStartElapsedMs = SystemClock.elapsedRealtime();
  private static long activityOnCreateElapsedMs;
  private static long flutterEngineConfiguredElapsedMs;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    activityOnCreateElapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    Log.i(STARTUP_TAG, "android_activity_on_create elapsedMs=" + activityOnCreateElapsedMs);
    super.onCreate(savedInstanceState);
  }

  @Override
  public void configureFlutterEngine(@NonNull FlutterEngine flutterEngine) {
    flutterEngineConfiguredElapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    Log.i(
        STARTUP_TAG,
        "android_flutter_engine_configured elapsedMs=" + flutterEngineConfiguredElapsedMs);
    super.configureFlutterEngine(flutterEngine);
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/auth/one_tap")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              switch (call.method) {
                case "isAvailable":
                  result.success(false);
                  break;
                case "requestLoginToken":
                  result.error(
                      "one_tap_sdk_not_configured",
                      "One-tap login SDK is not configured for this build.",
                      null);
                  break;
                default:
                  result.notImplemented();
                  break;
              }
            });
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/runtime/local_dev_https_trust")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              if ("localEnvDebugRootCertificate".equals(call.method)) {
                result.success(readLocalEnvDebugRootCertificate());
                return;
              }
              result.notImplemented();
            });
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/share/native_bridge")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              switch (call.method) {
                case "getCapability":
                  result.success(nativeShareCapability(call));
                  break;
                case "shareText":
                  result.success(nativeShareText(call));
                  break;
                default:
                  result.notImplemented();
                  break;
              }
            });
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/startup/deferred_plugins")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              switch (call.method) {
                case "ensureRtc":
                  StartupDeferredPluginRegistry.ensureRtc(flutterEngine);
                  result.success(null);
                  break;
                case "ensureContentEntry":
                  StartupDeferredPluginRegistry.ensureContentEntry(flutterEngine);
                  result.success(null);
                  break;
                case "ensureLocation":
                  StartupDeferredPluginRegistry.ensureLocation(flutterEngine);
                  result.success(null);
                  break;
                default:
                  result.notImplemented();
                  break;
              }
            });
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/startup/timings")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              if ("readProcessSegments".equals(call.method)) {
                Map<String, Object> payload = new HashMap<>();
                payload.put("androidActivityOnCreateMs", activityOnCreateElapsedMs);
                payload.put(
                    "androidFlutterEngineConfiguredMs", flutterEngineConfiguredElapsedMs);
                result.success(payload);
                return;
              }
              result.notImplemented();
            });
  }

  private Map<String, Object> nativeShareCapability(MethodCall call) {
    Map<String, Object> payload = new HashMap<>();
    String target = stringArgument(call, "target");
    payload.put("target", target);
    if (!isWeChatInstalled()) {
      payload.put("available", false);
      payload.put("reason", "wechat_not_installed");
      return payload;
    }
    payload.put("available", true);
    payload.put("reason", "android_intent");
    return payload;
  }

  private Map<String, Object> nativeShareText(MethodCall call) {
    Map<String, Object> payload = new HashMap<>();
    String target = stringArgument(call, "target");
    String text = stringArgument(call, "text");
    String subject = stringArgument(call, "subject");
    payload.put("target", target);
    if (!isWeChatInstalled()) {
      payload.put("delivered", false);
      payload.put("reason", "wechat_not_installed");
      return payload;
    }
    Intent intent = new Intent(Intent.ACTION_SEND);
    intent.setType("text/plain");
    intent.putExtra(Intent.EXTRA_TEXT, text);
    if (!subject.isEmpty()) {
      intent.putExtra(Intent.EXTRA_SUBJECT, subject);
    }
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    if ("wechatMoments".equals(target)) {
      intent.setClassName(WECHAT_PACKAGE, WECHAT_MOMENTS_ACTIVITY);
    } else {
      intent.setClassName(WECHAT_PACKAGE, WECHAT_FRIEND_ACTIVITY);
    }
    try {
      startActivity(intent);
      payload.put("delivered", true);
      payload.put("reason", "android_intent");
    } catch (ActivityNotFoundException error) {
      payload.put("delivered", false);
      payload.put("reason", "activity_not_found");
    }
    return payload;
  }

  private boolean isWeChatInstalled() {
    try {
      getPackageManager().getPackageInfo(WECHAT_PACKAGE, 0);
      return true;
    } catch (PackageManager.NameNotFoundException error) {
      return false;
    }
  }

  private String stringArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value == null ? "" : value.toString().trim();
  }

  private byte[] readLocalEnvDebugRootCertificate() {
    int resourceId =
        getResources().getIdentifier("local_env_debug_root", "raw", getPackageName());
    if (resourceId == 0) {
      return null;
    }
    try (InputStream input = getResources().openRawResource(resourceId);
        ByteArrayOutputStream output = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[8192];
      int read;
      while ((read = input.read(buffer)) != -1) {
        output.write(buffer, 0, read);
      }
      return output.toByteArray();
    } catch (Exception ignored) {
      return null;
    }
  }
}
