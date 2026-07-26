package com.quwoquan.quwoquan_app;

import android.content.Context;
import androidx.annotation.NonNull;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.MethodChannel;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

/** Android 来电能力桥；后台展示本身由 Firebase background engine + CallKit 插件负责。 */
final class IncomingCallNativeBridgePlugin {
  private IncomingCallNativeBridgePlugin() {}

  static void register(
      @NonNull FlutterEngine flutterEngine, @NonNull Context applicationContext) {
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/rtc/incoming_call")
        .setMethodCallHandler(
            (call, result) -> {
              switch (call.method) {
                case "readIncomingCallCapability":
                  Map<String, Object> capability = new HashMap<>();
                  capability.put(
                      "backgroundPushConfigured",
                      hasFirebaseApplicationId(applicationContext));
                  result.success(capability);
                  break;
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

  private static boolean hasFirebaseApplicationId(Context context) {
    int resourceId =
        context
            .getResources()
            .getIdentifier("google_app_id", "string", context.getPackageName());
    if (resourceId == 0) {
      return false;
    }
    String applicationId = context.getString(resourceId);
    return applicationId != null && !applicationId.trim().isEmpty();
  }
}
