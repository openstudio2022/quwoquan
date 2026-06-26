package com.quwoquan.quwoquan_app;

import android.os.Bundle;
import androidx.annotation.NonNull;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

public class MainActivity extends FlutterFragmentActivity {
  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
  }

  @Override
  public void configureFlutterEngine(@NonNull FlutterEngine flutterEngine) {
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
