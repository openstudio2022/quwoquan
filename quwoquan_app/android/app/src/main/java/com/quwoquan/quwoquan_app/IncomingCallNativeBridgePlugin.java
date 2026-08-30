package com.quwoquan.quwoquan_app;

import androidx.annotation.NonNull;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.MethodChannel;
import java.util.Collections;
/** Android 来电能力桥；后台展示本身由 Firebase background engine + CallKit 插件负责。 */
final class IncomingCallNativeBridgePlugin {
  private IncomingCallNativeBridgePlugin() {}

  static void register(@NonNull FlutterEngine flutterEngine) {
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/rtc/incoming_call")
        .setMethodCallHandler(
            (call, result) -> {
              switch (call.method) {
                case "readPendingIncomingCalls":
                case "consumePendingIncomingCallActions":
                case "readPushEndpointMutations":
                  result.success(Collections.emptyList());
                  break;
                case "setIncomingCallFlutterReady":
                case "ackPushEndpointMutation":
                case "queueActivePushEndpointRemovals":
                  result.success(null);
                  break;
                case "purgePushEndpointStateForTerminalAccountClosure":
                  result.success(true);
                  break;
                default:
                  result.notImplemented();
                  break;
              }
            });
  }
}
