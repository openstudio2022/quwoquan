package com.quwoquan.quwoquan_app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import androidx.annotation.NonNull;
import com.google.android.gms.auth.api.phone.SmsRetriever;
import com.google.android.gms.common.api.CommonStatusCodes;
import com.google.android.gms.common.api.Status;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.util.HashMap;
import java.util.Map;

final class SmsRetrieverOtpPlugin {
  private static final String CHANNEL = "quwoquan/auth/sms_retriever";

  private final Context context;
  private final MethodChannel channel;
  private BroadcastReceiver receiver;

  SmsRetrieverOtpPlugin(@NonNull Context context, @NonNull FlutterEngine engine) {
    this.context = context.getApplicationContext();
    this.channel =
        new MethodChannel(engine.getDartExecutor().getBinaryMessenger(), CHANNEL);
    this.channel.setMethodCallHandler(this::handle);
  }

  private void handle(MethodCall call, MethodChannel.Result result) {
    switch (call.method) {
      case "start":
        start(result);
        break;
      case "stop":
        stop();
        result.success(null);
        break;
      default:
        result.notImplemented();
        break;
    }
  }

  private void start(MethodChannel.Result result) {
    stop();
    receiver =
        new BroadcastReceiver() {
          @Override
          public void onReceive(Context receiverContext, Intent intent) {
            if (!SmsRetriever.SMS_RETRIEVED_ACTION.equals(intent.getAction())) return;
            Bundle extras = intent.getExtras();
            if (extras == null) return;
            Status status = readStatus(extras);
            if (status == null || status.getStatusCode() != CommonStatusCodes.SUCCESS) return;
            String message = extras.getString(SmsRetriever.EXTRA_SMS_MESSAGE, "");
            if (message.isEmpty()) return;
            Map<String, Object> payload = new HashMap<>();
            payload.put("message", message);
            channel.invokeMethod("smsRetrieved", payload);
            stop();
          }
        };
    IntentFilter filter = new IntentFilter(SmsRetriever.SMS_RETRIEVED_ACTION);
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      context.registerReceiver(
          receiver,
          filter,
          SmsRetriever.SEND_PERMISSION,
          null,
          Context.RECEIVER_EXPORTED);
    } else {
      context.registerReceiver(receiver, filter, SmsRetriever.SEND_PERMISSION, null);
    }
    SmsRetriever.getClient(context)
        .startSmsRetriever()
        .addOnSuccessListener(ignored -> result.success(null))
        .addOnFailureListener(
            error -> {
              stop();
              result.error("sms_retriever_unavailable", "SMS Retriever unavailable", null);
            });
  }

  private static Status readStatus(Bundle extras) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      return extras.getParcelable(SmsRetriever.EXTRA_STATUS, Status.class);
    }
    return readLegacyStatus(extras);
  }

  @SuppressWarnings("deprecation")
  private static Status readLegacyStatus(Bundle extras) {
    return extras.getParcelable(SmsRetriever.EXTRA_STATUS);
  }

  void stop() {
    BroadcastReceiver current = receiver;
    receiver = null;
    if (current == null) return;
    try {
      context.unregisterReceiver(current);
    } catch (IllegalArgumentException ignored) {
      // Already detached by the platform.
    }
  }
}
