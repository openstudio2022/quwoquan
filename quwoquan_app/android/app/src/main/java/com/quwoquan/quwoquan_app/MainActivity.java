package com.quwoquan.quwoquan_app;

import android.graphics.drawable.Drawable;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import androidx.annotation.NonNull;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.engine.renderer.FlutterUiDisplayListener;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

public class MainActivity extends FlutterFragmentActivity {
  private static final String STARTUP_TAG = "QWQStartup";
  private static final long MIN_NATIVE_WELCOME_MS = 0L;
  private static final long MAX_FLUTTER_WELCOME_READY_WAIT_MS = 4500L;
  private long activityCreateMs = 0L;
  private long nativeStartupStartedElapsedRealtime = 0L;
  private View startupOverlay;
  private boolean flutterUiDisplayed = false;
  private boolean flutterWelcomeReady = false;
  private boolean overlayRemovalCheckScheduled = false;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    activityCreateMs = SystemClock.uptimeMillis();
    nativeStartupStartedElapsedRealtime =
        getIntent().getLongExtra("nativeStartupStartedElapsedRealtime", 0L);
    Log.i(STARTUP_TAG, "android_activity_on_create");
    getWindow().setBackgroundDrawable(createStartupBackgroundDrawable());
    super.onCreate(savedInstanceState);
    installStartupOverlay();
    tryRemoveStartupOverlay();
  }

  @Override
  public void configureFlutterEngine(@NonNull FlutterEngine flutterEngine) {
    super.configureFlutterEngine(flutterEngine);
    Log.i(
        STARTUP_TAG,
        "android_flutter_engine_configured elapsedMs="
            + (SystemClock.uptimeMillis() - activityCreateMs));
    FlutterUiDisplayListener startupDisplayListener =
        new FlutterUiDisplayListener() {
          @Override
          public void onFlutterUiDisplayed() {
            Log.i(
                STARTUP_TAG,
                "android_flutter_ui_displayed elapsedMs="
                    + (SystemClock.uptimeMillis() - activityCreateMs));
            flutterUiDisplayed = true;
            tryRemoveStartupOverlay();
            flutterEngine
                .getRenderer()
                .removeIsDisplayingFlutterUiListener(this);
            reportFullyDrawn();
          }

          @Override
          public void onFlutterUiNoLongerDisplayed() {}
        };
    flutterEngine
        .getRenderer()
        .addIsDisplayingFlutterUiListener(startupDisplayListener);
    if (flutterEngine.getRenderer().isDisplayingFlutterUi()) {
      startupDisplayListener.onFlutterUiDisplayed();
    }
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
            "quwoquan/startup/native")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              if ("nativeStartupElapsedMs".equals(call.method)) {
                if (nativeStartupStartedElapsedRealtime <= 0L) {
                  result.success(null);
                  return;
                }
                result.success(SystemClock.uptimeMillis() - nativeStartupStartedElapsedRealtime);
                return;
              }
              if ("flutterWelcomeReady".equals(call.method)) {
                flutterWelcomeReady = true;
                Log.i(
                    STARTUP_TAG,
                    "android_flutter_welcome_ready elapsedMs="
                        + nativeStartupElapsedMs()
                        + " sequenceElapsedMs="
                        + argumentLong(call, "sequenceElapsedMs"));
                runOnUiThread(this::tryRemoveStartupOverlay);
                result.success(true);
                return;
              }
              if ("flutterWelcomeCompleted".equals(call.method)) {
                Log.i(
                    STARTUP_TAG,
                    "android_native_welcome_completion_received elapsedMs="
                        + nativeStartupElapsedMs());
                runOnUiThread(this::tryRemoveStartupOverlay);
                result.success(true);
                return;
              }
              result.notImplemented();
            });
  }

  private void installStartupOverlay() {
    if (startupOverlay != null) {
      return;
    }
    NativeWelcomeView overlay =
        new NativeWelcomeView(this, nativeStartupStartedElapsedRealtime);

    addContentView(
        overlay,
        new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    startupOverlay = overlay;
    Log.i(
        STARTUP_TAG,
        "android_native_welcome_host_installed elapsedMs="
            + (SystemClock.uptimeMillis() - activityCreateMs));
  }

  private Drawable createStartupBackgroundDrawable() {
    return getResources().getDrawable(R.drawable.launch_background, getTheme());
  }

  private void tryRemoveStartupOverlay() {
    final View overlay = startupOverlay;
    if (overlay == null || !flutterUiDisplayed) {
      return;
    }
    final long elapsedMs = nativeStartupElapsedMs();
    if (!flutterWelcomeReady && elapsedMs < MAX_FLUTTER_WELCOME_READY_WAIT_MS) {
      scheduleOverlayRemovalCheck(120L);
      return;
    }
    if (!flutterWelcomeReady) {
      Log.w(
          STARTUP_TAG,
          "android_flutter_welcome_ready_timeout elapsedMs=" + elapsedMs);
    }
    if (elapsedMs < MIN_NATIVE_WELCOME_MS) {
      scheduleOverlayRemovalCheck(MIN_NATIVE_WELCOME_MS - elapsedMs);
      return;
    }
    removeStartupOverlay();
  }

  private void scheduleOverlayRemovalCheck(long delayMs) {
    if (overlayRemovalCheckScheduled || startupOverlay == null) {
      return;
    }
    overlayRemovalCheckScheduled = true;
    startupOverlay.postDelayed(
        () -> {
          overlayRemovalCheckScheduled = false;
          tryRemoveStartupOverlay();
        },
        Math.max(16L, delayMs));
  }

  private long nativeStartupElapsedMs() {
    final long startedAt =
        nativeStartupStartedElapsedRealtime > 0L
            ? nativeStartupStartedElapsedRealtime
            : activityCreateMs;
    return Math.max(0L, SystemClock.uptimeMillis() - startedAt);
  }

  private long argumentLong(MethodCall call, String key) {
    Object value = call.argument(key);
    if (value instanceof Number) {
      return ((Number) value).longValue();
    }
    return 0L;
  }

  private void removeStartupOverlay() {
    final View overlay = startupOverlay;
    if (overlay == null) {
      return;
    }
    startupOverlay = null;
    overlayRemovalCheckScheduled = false;
    overlay
        .animate()
        .alpha(0f)
        .setDuration(120L)
        .withEndAction(
            () -> {
              ViewGroup parent = (ViewGroup) overlay.getParent();
              if (parent != null) {
                parent.removeView(overlay);
              }
            })
        .start();
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
