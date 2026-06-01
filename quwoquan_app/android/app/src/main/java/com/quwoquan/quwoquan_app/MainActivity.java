package com.quwoquan.quwoquan_app;

import androidx.annotation.NonNull;
import io.flutter.embedding.android.FlutterActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;

public class MainActivity extends FlutterActivity {
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
  }
}
