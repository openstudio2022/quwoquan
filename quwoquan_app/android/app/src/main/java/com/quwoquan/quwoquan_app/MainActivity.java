package com.quwoquan.quwoquan_app;

import android.content.Intent;
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
  private static final long processStartElapsedMs = SystemClock.elapsedRealtime();
  private static long activityOnCreateElapsedMs;
  private static long flutterEngineConfiguredElapsedMs;
  private WechatSdkCoordinator wechatSdkCoordinator;
  private CommercialAuthPlugin commercialAuthPlugin;
  private AliyunOneTapPlugin aliyunOneTapPlugin;

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
    registerStartupTimingsChannel(flutterEngine);
    super.configureFlutterEngine(flutterEngine);
    wechatSdkCoordinator = new WechatSdkCoordinator(this);
    commercialAuthPlugin = new CommercialAuthPlugin(this, wechatSdkCoordinator);
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/auth/native_bridge")
        .setMethodCallHandler(commercialAuthPlugin::handle);
    aliyunOneTapPlugin = new AliyunOneTapPlugin(this);
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/auth/one_tap")
        .setMethodCallHandler(aliyunOneTapPlugin::handle);
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
                  result.success(
                      wechatSdkCoordinator.capability(stringArgument(call, "target")));
                  break;
                case "shareWebpageCard":
                  result.success(wechatSdkCoordinator.shareWebpageCard(call));
                  break;
                case "consumePendingOutcomes":
                  result.success(wechatSdkCoordinator.consumePendingOutcomes());
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
  }

  private void registerStartupTimingsChannel(@NonNull FlutterEngine flutterEngine) {
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
                payload.put(
                    "elapsedSinceProcessStartMs",
                    SystemClock.elapsedRealtime() - processStartElapsedMs);
                payload.put("deadlineOrigin", "android_process");
                result.success(payload);
                return;
              }
              if ("recordStartupEvent".equals(call.method)) {
                Object event = call.arguments;
                Log.i(STARTUP_TAG, "startup_event " + (event == null ? "{}" : event));
                result.success(null);
                return;
              }
              result.notImplemented();
            });
  }

  @Override
  protected void onActivityResult(int requestCode, int resultCode, Intent data) {
    if (commercialAuthPlugin != null
        && commercialAuthPlugin.onActivityResult(requestCode, resultCode, data)) {
      return;
    }
    super.onActivityResult(requestCode, resultCode, data);
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
