package com.quwoquan.quwoquan_app;

import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.TextView;
import androidx.annotation.NonNull;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.engine.renderer.FlutterUiDisplayListener;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends FlutterFragmentActivity {
  private static final String STARTUP_TAG = "QWQStartup";
  // 所有构建都使用同一进程钟硬门。Debug/JIT 慢启动必须收紧关键路径，
  // 不能用更长 timeout 掩盖并让原生、Dart 状态机出现双时钟。
  private static final long FLUTTER_FIRST_FRAME_DEADLINE_MS = 6000L;
  private static final long NATIVE_TERMINAL_RECONCILIATION_WINDOW_MS = 120L;
  private static final String NATIVE_RECOVERY_VIEW_TAG = "qwq_native_startup_recovery";
  private static final Pattern STARTUP_EVENT_NAME_PATTERN =
      Pattern.compile("\"eventName\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final Pattern STARTUP_EVENT_PHASE_PATTERN =
      Pattern.compile("\"phase\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final Pattern STARTUP_EVENT_EXIT_REASON_PATTERN =
      Pattern.compile("\"exitReason\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final Pattern STARTUP_EVENT_FAILURE_CODE_PATTERN =
      Pattern.compile("\"failureCode\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final long STARTUP_PROBE_MAX_DURATION_MS = 300000L;
  private static final long processStartElapsedMs = SystemClock.elapsedRealtime();
  private static long activityOnCreateElapsedMs;
  private static long flutterEngineConfiguredElapsedMs;
  private final Handler startupHandler = new Handler(Looper.getMainLooper());
  private final ScheduledExecutorService startupWatchdogExecutor =
      Executors.newSingleThreadScheduledExecutor(
          runnable -> {
            Thread thread = new Thread(runnable, "qwq-startup-watchdog");
            thread.setDaemon(true);
            return thread;
          });
  private StartupNativeTelemetryJournal startupTelemetryJournal;
  private WechatSdkCoordinator wechatSdkCoordinator;
  private CommercialAuthPlugin commercialAuthPlugin;
  private AliyunOneTapPlugin aliyunOneTapPlugin;
  private CellularNetworkProbePlugin cellularNetworkProbePlugin;
  private ScheduledFuture<?> flutterFirstFrameWatchdog;
  private ScheduledFuture<?> nativeRecoveryTerminalReconciliation;
  private FlutterEngine startupFlutterEngine;
  private FlutterUiDisplayListener flutterUiDisplayListener;
  private volatile boolean flutterFirstFrameConfirmed;
  private volatile boolean startupSafeTerminalConfirmed;
  private volatile boolean appInForeground;
  private volatile boolean nativeRecoveryShown;
  private volatile boolean nativeRecoveryDeadlineReached;
  private long firstFrameForegroundRemainingMs = FLUTTER_FIRST_FRAME_DEADLINE_MS;
  private long foregroundStartedElapsedMs;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    activityOnCreateElapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    Log.i(STARTUP_TAG, "android_activity_on_create elapsedMs=" + activityOnCreateElapsedMs);
    super.onCreate(savedInstanceState);
    startupTelemetryJournal = new StartupNativeTelemetryJournal(this);
    startupTelemetryJournal.record(
        "native_pre_flutter",
        activityOnCreateElapsedMs,
        "observed",
        "",
        "",
        "",
        "android_process");
    appInForeground = true;
    // 首帧预算必须从进程最早可得的 monotonic 时钟开始，而不是 onResume 后重新给 6 秒。
    foregroundStartedElapsedMs = processStartElapsedMs;
    armFlutterFirstFrameWatchdog();
  }

  @Override
  public void configureFlutterEngine(@NonNull FlutterEngine flutterEngine) {
    flutterEngineConfiguredElapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    Log.i(
        STARTUP_TAG,
        "android_flutter_engine_configured elapsedMs=" + flutterEngineConfiguredElapsedMs);
    registerStartupTimingsChannel(flutterEngine);
    observeNativeFlutterFirstFrame(flutterEngine);
    // Gradle 在构建期通过 patch_android_plugin_registrant.sh 从 generated registrant
    // 剥离首帧后基础组（SecureStorage/Prefs/设备与网络探测）和 feature-demand 组。
    // bootstrap 只能使用 native timing/journal bridge；基础组由 post-frame barrier 装配。
    super.configureFlutterEngine(flutterEngine);
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/auth/native_bridge")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) ->
                commercialAuthPlugin().handle(call, result));
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/auth/one_tap")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) ->
                aliyunOneTapPlugin().handle(call, result));
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
                      wechatSdkCoordinator().capability(stringArgument(call, "target")));
                  break;
                case "shareWebpageCard":
                  result.success(wechatSdkCoordinator().shareWebpageCard(call));
                  break;
                case "consumePendingOutcomes":
                  result.success(wechatSdkCoordinator().consumePendingOutcomes());
                  break;
                default:
                  result.notImplemented();
                  break;
              }
            });
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/network/cellular_generation")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) ->
                cellularNetworkProbePlugin().handle(call, result));
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/startup/deferred_plugins")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              switch (call.method) {
                case "ensureStartupPostFirstFrame":
                  completeDeferredPluginRegistration(
                      result,
                      "startup_post_first_frame",
                      StartupDeferredPluginRegistry.ensureStartupPostFirstFrame(flutterEngine));
                  break;
                case "ensureRtc":
                  completeDeferredPluginRegistration(
                      result,
                      "rtc",
                      StartupDeferredPluginRegistry.ensureRtc(flutterEngine));
                  break;
                case "ensureContentEntry":
                  completeDeferredPluginRegistration(
                      result,
                      "content_entry",
                      StartupDeferredPluginRegistry.ensureContentEntry(flutterEngine));
                  break;
                case "ensureLocation":
                  completeDeferredPluginRegistration(
                      result,
                      "location",
                      StartupDeferredPluginRegistry.ensureLocation(flutterEngine));
                  break;
                default:
                  result.notImplemented();
                  break;
              }
            });
  }

  private void completeDeferredPluginRegistration(
      MethodChannel.Result result, String group, boolean attached) {
    if (attached) {
      result.success(null);
      return;
    }
    result.error(
        "startup_deferred_plugin_unavailable",
        "Deferred plugin group is not attached: " + group,
        null);
  }

  private WechatSdkCoordinator wechatSdkCoordinator() {
    if (wechatSdkCoordinator == null) {
      wechatSdkCoordinator = new WechatSdkCoordinator(this);
    }
    return wechatSdkCoordinator;
  }

  private CommercialAuthPlugin commercialAuthPlugin() {
    if (commercialAuthPlugin == null) {
      commercialAuthPlugin = new CommercialAuthPlugin(this, wechatSdkCoordinator());
    }
    return commercialAuthPlugin;
  }

  private AliyunOneTapPlugin aliyunOneTapPlugin() {
    if (aliyunOneTapPlugin == null) {
      aliyunOneTapPlugin = new AliyunOneTapPlugin(this);
    }
    return aliyunOneTapPlugin;
  }

  private CellularNetworkProbePlugin cellularNetworkProbePlugin() {
    if (cellularNetworkProbePlugin == null) {
      cellularNetworkProbePlugin = new CellularNetworkProbePlugin(this);
    }
    return cellularNetworkProbePlugin;
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
                if (startupTelemetryJournal != null) {
                  payload.put("startupAttemptId", startupTelemetryJournal.attemptId());
                }
                result.success(payload);
                return;
              }
              if ("readStartupJournal".equals(call.method)) {
                Map<String, Object> payload = new HashMap<>();
                if (startupTelemetryJournal != null) {
                  payload.put("attemptId", startupTelemetryJournal.attemptId());
                  payload.put("events", startupTelemetryJournal.events());
                } else {
                  payload.put("attemptId", "");
                  payload.put("events", new ArrayList<String>());
                }
                result.success(payload);
                return;
              }
              if ("clearStartupJournal".equals(call.method)) {
                if (startupTelemetryJournal != null) {
                  startupTelemetryJournal.clearEvents();
                }
                result.success(null);
                return;
              }
              if ("recordStartupEvent".equals(call.method)) {
                Object event = call.arguments;
                logSafeStartupEvent(event);
                if (isFlutterFirstFrameEvent(event)) {
                  confirmFlutterFirstFrame("dart_channel");
                }
                if (isStartupSafeTerminalEvent(event)) {
                  confirmStartupSafeTerminal();
                }
                result.success(null);
                return;
              }
              result.notImplemented();
            });
  }

  @Override
  protected void onResume() {
    super.onResume();
    if (!appInForeground) {
      appInForeground = true;
      foregroundStartedElapsedMs = SystemClock.elapsedRealtime();
    }
    armFlutterFirstFrameWatchdog();
  }

  @Override
  protected void onPause() {
    if (appInForeground && !flutterFirstFrameConfirmed) {
      consumeForegroundFirstFrameBudget(SystemClock.elapsedRealtime());
    }
    appInForeground = false;
    foregroundStartedElapsedMs = 0L;
    cancelFlutterFirstFrameWatchdog();
    super.onPause();
  }

  @Override
  protected void onDestroy() {
    cancelFlutterFirstFrameWatchdog();
    cancelNativeRecoveryTerminalReconciliation();
    if (startupFlutterEngine != null && flutterUiDisplayListener != null) {
      startupFlutterEngine
          .getRenderer()
          .removeIsDisplayingFlutterUiListener(flutterUiDisplayListener);
    }
    startupFlutterEngine = null;
    flutterUiDisplayListener = null;
    if (cellularNetworkProbePlugin != null) {
      cellularNetworkProbePlugin.dispose();
    }
    startupWatchdogExecutor.shutdownNow();
    super.onDestroy();
  }

  private boolean isFlutterFirstFrameEvent(Object event) {
    return event instanceof String
        && ((String) event).contains("\"eventName\":\"flutter_first_frame\"");
  }

  private boolean isStartupSafeTerminalEvent(Object event) {
    return event instanceof String
        && ((String) event).contains("\"eventName\":\"startup_safe_terminal\"");
  }

  private void logSafeStartupEvent(Object rawEvent) {
    if (!(rawEvent instanceof String)) {
      return;
    }
    String event = (String) rawEvent;
    Matcher eventNameMatcher = STARTUP_EVENT_NAME_PATTERN.matcher(event);
    if (!eventNameMatcher.find()) {
      return;
    }
    String eventName = eventNameMatcher.group(1);
    if ("startup_bootstrap_failure".equals(eventName)) {
      // bootstrap 根已经显示 Flutter recovery；只输出稳定错误码，不转写异常或用户态上下文。
      Log.i(
          STARTUP_TAG,
          "startup_probe phase=bootstrap_failure"
              + safeStartupFailureCodeSuffix(event));
      return;
    }
    if (!"startup_welcome_sequence".equals(eventName)) {
      Log.i(STARTUP_TAG, "startup_event_received eventName=" + eventName);
      return;
    }
    logSafeStartupProbeTerminal(event);
    // 原生层只确认 Flutter 启动事件到达；probe 仅可见终态，不镜像动效 phase/replay。
    Log.i(STARTUP_TAG, "startup_event_received eventName=startup_welcome_sequence");
  }

  private void logSafeStartupProbeTerminal(String rawEvent) {
    Matcher phaseMatcher = STARTUP_EVENT_PHASE_PATTERN.matcher(rawEvent);
    if (!phaseMatcher.find()) {
      return;
    }
    String phase = phaseMatcher.group(1);
    switch (phase) {
      case "finished":
        long welcomeExitMs =
            readSafeStartupProbeDuration(rawEvent, "welcomeExitMs", "elapsedSinceProcessStartMs");
        if (welcomeExitMs < 0L) {
          return;
        }
        String exitReason = readSafeStartupProbeExitReason(rawEvent);
        Log.i(
            STARTUP_TAG,
            "startup_probe phase=finished welcomeExitMs="
                + welcomeExitMs
                + (exitReason.isEmpty() ? "" : " exitReason=" + exitReason));
        return;
      case "main_shell_first_paint":
        long shellFirstPaintMs =
            readSafeStartupProbeDuration(
                rawEvent, "shellFirstPaintMs", "elapsedSinceProcessStartMs");
        if (shellFirstPaintMs >= 0L) {
          Log.i(
              STARTUP_TAG,
              "startup_probe phase=main_shell_first_paint shellFirstPaintMs="
                  + shellFirstPaintMs);
        }
        return;
      case "welcome_overlay_removed":
        long overlayRemovedMs =
            readSafeStartupProbeDuration(
                rawEvent, "overlayRemovedMs", "elapsedSinceProcessStartMs");
        if (overlayRemovedMs >= 0L) {
          Log.i(
              STARTUP_TAG,
              "startup_probe phase=welcome_overlay_removed overlayRemovedMs="
                  + overlayRemovedMs);
        }
        return;
      case "safe_recovery_shown":
        Log.i(
            STARTUP_TAG,
            "startup_probe phase=safe_recovery_shown"
                + safeStartupFailureCodeSuffix(rawEvent));
        return;
      default:
        return;
    }
  }

  private long readSafeStartupProbeDuration(
      String rawEvent, String preferredField, String fallbackField) {
    long preferred = readSafeStartupProbeInteger(rawEvent, preferredField);
    return preferred >= 0L ? preferred : readSafeStartupProbeInteger(rawEvent, fallbackField);
  }

  private long readSafeStartupProbeInteger(String rawEvent, String field) {
    Matcher matcher =
        Pattern.compile("\"" + Pattern.quote(field) + "\"\\s*:\\s*(\\d+)").matcher(rawEvent);
    if (!matcher.find()) {
      return -1L;
    }
    try {
      long value = Long.parseLong(matcher.group(1));
      return value <= STARTUP_PROBE_MAX_DURATION_MS ? value : -1L;
    } catch (NumberFormatException ignored) {
      return -1L;
    }
  }

  private String readSafeStartupProbeExitReason(String rawEvent) {
    Matcher matcher = STARTUP_EVENT_EXIT_REASON_PATTERN.matcher(rawEvent);
    if (!matcher.find()) {
      return "";
    }
    String value = matcher.group(1);
    switch (value) {
      case "ready_primary":
      case "ready_replay":
      case "deadline":
      case "deadline_fallback":
        return value;
      default:
        return "";
    }
  }

  private String safeStartupFailureCodeSuffix(String rawEvent) {
    Matcher matcher = STARTUP_EVENT_FAILURE_CODE_PATTERN.matcher(rawEvent);
    if (!matcher.find()) {
      return "";
    }
    String failureCode = matcher.group(1);
    return failureCode.length() <= 128 ? " failureCode=" + failureCode : "";
  }

  private void observeNativeFlutterFirstFrame(@NonNull FlutterEngine flutterEngine) {
    if (startupFlutterEngine != null && flutterUiDisplayListener != null) {
      startupFlutterEngine
          .getRenderer()
          .removeIsDisplayingFlutterUiListener(flutterUiDisplayListener);
    }
    startupFlutterEngine = flutterEngine;
    flutterUiDisplayListener =
        new FlutterUiDisplayListener() {
          @Override
          public void onFlutterUiDisplayed() {
            confirmFlutterFirstFrame("renderer");
          }

          @Override
          public void onFlutterUiNoLongerDisplayed() {
            // 首帧是一次性事实；后续 surface 切换不能重新打开 watchdog。
          }
        };
    flutterEngine
        .getRenderer()
        .addIsDisplayingFlutterUiListener(flutterUiDisplayListener);
  }

  private void confirmFlutterFirstFrame(@NonNull String source) {
    if (flutterFirstFrameConfirmed) {
      return;
    }
    // 原生 watchdog 只守护 renderer 首帧。safe terminal 较慢交由 Flutter
    // 安全状态机处理，绝不能覆盖已经可见的 Flutter UI。
    flutterFirstFrameConfirmed = true;
    cancelFlutterFirstFrameWatchdog();
    dismissNativeStartupRecoveryAfterFlutterFirstFrame();
    Log.i(
        STARTUP_TAG,
        "android_flutter_first_frame elapsedMs="
            + (SystemClock.elapsedRealtime() - processStartElapsedMs)
            + " source="
            + source);
  }

  private void confirmStartupSafeTerminal() {
    if (startupSafeTerminalConfirmed) {
      return;
    }
    // MethodChannel 可能比 watchdog 主线程任务晚几毫秒。只要 Flutter 已到
    // routerShell / recovery 安全面，就必须取消看门狗并撤销竞态恢复层。
    startupSafeTerminalConfirmed = true;
    cancelFlutterFirstFrameWatchdog();
    cancelNativeRecoveryTerminalReconciliation();
    dismissNativeStartupRecoveryForSafeTerminalRace();
    long elapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    if (flutterFirstFrameConfirmed && elapsedMs > FLUTTER_FIRST_FRAME_DEADLINE_MS) {
      recordStartupSafeTerminalSlow(elapsedMs);
    }
    Log.i(
        STARTUP_TAG,
        "android_startup_safe_terminal elapsedMs="
            + elapsedMs);
  }

  private void recordStartupSafeTerminalSlow(long elapsedMs) {
    Log.w(STARTUP_TAG, "android_startup_safe_terminal_slow elapsedMs=" + elapsedMs);
    if (startupTelemetryJournal == null) {
      return;
    }
    startupTelemetryJournal.record(
        "terminal",
        elapsedMs,
        "safe_terminal_slow",
        "flutter_visible",
        "",
        "native_watchdog",
        "android_process");
  }

  private void dismissNativeStartupRecoveryForSafeTerminalRace() {
    if (!nativeRecoveryShown) {
      nativeRecoveryDeadlineReached = false;
      return;
    }
    ViewGroup root = (ViewGroup) getWindow().getDecorView();
    View recovery = root.findViewWithTag(NATIVE_RECOVERY_VIEW_TAG);
    if (recovery != null) {
      root.removeView(recovery);
    }
    nativeRecoveryShown = false;
    nativeRecoveryDeadlineReached = false;
    Log.i(STARTUP_TAG, "android_startup_safe_terminal_race_dismissed");
  }

  private void dismissNativeStartupRecoveryAfterFlutterFirstFrame() {
    if (!nativeRecoveryShown) {
      nativeRecoveryDeadlineReached = false;
      return;
    }
    ViewGroup root = (ViewGroup) getWindow().getDecorView();
    View recovery = root.findViewWithTag(NATIVE_RECOVERY_VIEW_TAG);
    if (recovery != null) {
      root.removeView(recovery);
    }
    nativeRecoveryShown = false;
    nativeRecoveryDeadlineReached = false;
    cancelNativeRecoveryTerminalReconciliation();
    Log.i(STARTUP_TAG, "android_native_recovery_dismissed_after_flutter_first_frame");
  }

  private void armFlutterFirstFrameWatchdog() {
    if (flutterFirstFrameConfirmed
        || startupSafeTerminalConfirmed
        || nativeRecoveryShown
        || nativeRecoveryDeadlineReached
        || !appInForeground) {
      return;
    }
    cancelFlutterFirstFrameWatchdog();
    final long remainingMs = consumeForegroundFirstFrameBudget(SystemClock.elapsedRealtime());
    if (remainingMs <= 0L) {
      triggerNativeFirstFrameDeadline();
      return;
    }
    flutterFirstFrameWatchdog =
        startupWatchdogExecutor.schedule(
            this::triggerNativeFirstFrameDeadline, remainingMs, TimeUnit.MILLISECONDS);
  }

  private void cancelFlutterFirstFrameWatchdog() {
    if (flutterFirstFrameWatchdog != null) {
      flutterFirstFrameWatchdog.cancel(false);
      flutterFirstFrameWatchdog = null;
    }
  }

  private void scheduleNativeRecoveryTerminal(
      long elapsedMs, boolean firstFrameMissing) {
    cancelNativeRecoveryTerminalReconciliation();
    nativeRecoveryTerminalReconciliation =
        startupWatchdogExecutor.schedule(
            () ->
                startupHandler.post(
                    () -> {
                      if (startupSafeTerminalConfirmed
                          || !nativeRecoveryShown
                          || !nativeRecoveryDeadlineReached) {
                        return;
                      }
                      recordNativeStartupTerminal(elapsedMs, firstFrameMissing);
                    }),
            NATIVE_TERMINAL_RECONCILIATION_WINDOW_MS,
            TimeUnit.MILLISECONDS);
  }

  private void cancelNativeRecoveryTerminalReconciliation() {
    if (nativeRecoveryTerminalReconciliation != null) {
      nativeRecoveryTerminalReconciliation.cancel(false);
      nativeRecoveryTerminalReconciliation = null;
    }
  }

  private long consumeForegroundFirstFrameBudget(long nowElapsedMs) {
    if (!appInForeground || flutterFirstFrameConfirmed || startupSafeTerminalConfirmed) {
      return firstFrameForegroundRemainingMs;
    }
    if (foregroundStartedElapsedMs > 0L) {
      final long foregroundElapsedMs = Math.max(0L, nowElapsedMs - foregroundStartedElapsedMs);
      firstFrameForegroundRemainingMs =
          Math.max(0L, firstFrameForegroundRemainingMs - foregroundElapsedMs);
      foregroundStartedElapsedMs = nowElapsedMs;
    }
    return firstFrameForegroundRemainingMs;
  }

  private synchronized void triggerNativeFirstFrameDeadline() {
    if (flutterFirstFrameConfirmed
        || startupSafeTerminalConfirmed
        || nativeRecoveryShown
        || nativeRecoveryDeadlineReached
        || !appInForeground) {
      return;
    }
    final long elapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    // 必须在主线程再次核对 renderer 首帧；后台任务与首帧回调竞争时，
    // 只要已有 Flutter UI，就绝不能显示 native recovery。
    startupHandler.post(
        () -> {
          if (flutterFirstFrameConfirmed
              || startupSafeTerminalConfirmed
              || nativeRecoveryShown
              || nativeRecoveryDeadlineReached
              || !appInForeground) {
            return;
          }
          nativeRecoveryDeadlineReached = true;
          recordNativeStartupDeadline(elapsedMs, true);
          showNativeStartupRecovery(elapsedMs, false);
        });
  }

  private void recordNativeStartupDeadline(long elapsedMs, boolean firstFrameMissing) {
    if (!firstFrameMissing) return;
    Log.e(
        STARTUP_TAG,
        "android_native_first_frame_timeout elapsedMs=" + elapsedMs);
    if (startupTelemetryJournal == null) {
      return;
    }
    startupTelemetryJournal.record(
        "recovery",
        elapsedMs,
        "native_first_frame_timeout",
        "native_recovery",
        "OPS.SYSTEM.startup_native_first_frame_timeout",
        "native_watchdog",
        "android_process");
    // 先展示 native recovery；同一帧队列中若 safe_terminal 到达，不得留下
    // nativeRecovery 与 Flutter success 两个 terminal。
    scheduleNativeRecoveryTerminal(elapsedMs, firstFrameMissing);
  }

  private void recordNativeStartupTerminal(long elapsedMs, boolean firstFrameMissing) {
    if (startupTelemetryJournal == null || startupSafeTerminalConfirmed) {
      return;
    }
    if (!firstFrameMissing) return;
    startupTelemetryJournal.record(
        "terminal",
        elapsedMs,
        "native_first_frame_timeout",
        "native_recovery",
        "OPS.SYSTEM.startup_native_first_frame_timeout",
        "native_watchdog",
        "android_process");
  }

  private void showNativeStartupRecovery() {
    final long elapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    showNativeStartupRecovery(elapsedMs, true);
  }

  private void showNativeStartupRecovery(long elapsedMs, boolean recordDeadline) {
    if (flutterFirstFrameConfirmed
        || startupSafeTerminalConfirmed
        || nativeRecoveryShown
        || isFinishing()
        || isDestroyed()) {
      return;
    }
    nativeRecoveryShown = true;
    if (recordDeadline) {
      nativeRecoveryDeadlineReached = true;
      recordNativeStartupDeadline(elapsedMs, !flutterFirstFrameConfirmed);
    }

    ViewGroup root = (ViewGroup) getWindow().getDecorView();
    if (root.findViewWithTag(NATIVE_RECOVERY_VIEW_TAG) != null) {
      return;
    }
    FrameLayout recovery = new FrameLayout(this);
    recovery.setTag(NATIVE_RECOVERY_VIEW_TAG);
    recovery.setBackgroundColor(Color.rgb(10, 132, 255));

    TextView title = new TextView(this);
    title.setText("应用启动遇到问题");
    title.setTextColor(Color.WHITE);
    title.setTextSize(22);
    title.setGravity(Gravity.CENTER);
    FrameLayout.LayoutParams titleLayout =
        new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    titleLayout.gravity = Gravity.CENTER_HORIZONTAL | Gravity.CENTER_VERTICAL;
    titleLayout.bottomMargin = 84;
    recovery.addView(title, titleLayout);

    TextView message = new TextView(this);
    message.setText("暂未显示应用界面，请重试或重新打开应用。");
    message.setTextColor(Color.WHITE);
    message.setTextSize(15);
    message.setGravity(Gravity.CENTER);
    FrameLayout.LayoutParams messageLayout =
        new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    messageLayout.gravity = Gravity.CENTER_HORIZONTAL | Gravity.CENTER_VERTICAL;
    messageLayout.topMargin = 8;
    recovery.addView(message, messageLayout);

    Button retry = new Button(this);
    retry.setText("重新打开应用");
    retry.setOnClickListener(
        ignored -> {
          requestNewStartupAttempt();
        });
    FrameLayout.LayoutParams retryLayout =
        new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    retryLayout.gravity = Gravity.CENTER_HORIZONTAL | Gravity.CENTER_VERTICAL;
    retryLayout.topMargin = 104;
    recovery.addView(retry, retryLayout);
    root.addView(
        recovery,
        new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
  }

  private void requestNewStartupAttempt() {
    long elapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    if (startupTelemetryJournal != null) {
      startupTelemetryJournal.record(
          "terminal",
          elapsedMs,
          "restart_requested",
          "native_recovery",
          "OPS.SYSTEM.startup_native_first_frame_timeout",
          "native_retry",
          "android_process");
    }
    Intent launchIntent = getPackageManager().getLaunchIntentForPackage(getPackageName());
    if (launchIntent == null) {
      return;
    }
    launchIntent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    startActivity(launchIntent);
    finish();
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
