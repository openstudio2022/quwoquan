package com.quwoquan.quwoquan_app;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import androidx.annotation.NonNull;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.engine.renderer.FlutterUiDisplayListener;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONObject;

public class MainActivity extends FlutterFragmentActivity {
  private static final String STARTUP_TAG = "QWQStartup";
  // 所有构建都使用同一进程钟硬门。Debug/JIT 慢启动必须收紧关键路径，
  // 不能用更长 timeout 掩盖并让原生、Dart 状态机出现双时钟。
  private static final long FLUTTER_FIRST_FRAME_DEADLINE_MS = 3000L;
  private static final String RUNTIME_CRASH_MARKER_CHANNEL =
      "quwoquan/runtime/native_crash_marker";
  private static final String RUNTIME_CRASH_MARKER_PREFERENCES =
      "quwoquan.runtime.diagnostics";
  private static final String RUNTIME_ANR_CONSUMED_TIMESTAMP_KEY =
      "previous_native_anr_consumed_timestamp";
  private static final long RUNTIME_ANR_MAX_AGE_MS = TimeUnit.HOURS.toMillis(72);
  private static final Pattern STARTUP_EVENT_NAME_PATTERN =
      Pattern.compile("\"eventName\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final Pattern STARTUP_EVENT_PHASE_PATTERN =
      Pattern.compile("\"phase\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final Pattern STARTUP_EVENT_EXIT_REASON_PATTERN =
      Pattern.compile("\"exitReason\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final Pattern STARTUP_EVENT_FAILURE_CODE_PATTERN =
      Pattern.compile("\"failureCode\"\\s*:\\s*\"([A-Za-z0-9_.-]+)\"");
  private static final long STARTUP_PROBE_MAX_DURATION_MS = 300000L;
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
  private AssistantDeviceActionPlugin assistantDeviceActionPlugin;
  private RecoveryFailureEncryptedStore recoveryFailureEncryptedStore;
  private ScheduledFuture<?> flutterFirstFrameWatchdog;
  private FlutterEngine startupFlutterEngine;
  private FlutterUiDisplayListener flutterUiDisplayListener;
  private volatile boolean flutterFirstFrameConfirmed;
  private volatile boolean startupSafeTerminalConfirmed;
  private volatile boolean appInForeground;
  private volatile boolean nativeFirstFrameDeadlineReached;
  private volatile boolean dartStartupAttemptStarted;
  private volatile boolean currentDartAttemptIsHotRestart;
  private volatile String currentDartAttemptId = "";
  private volatile String currentLaunchMode = "unknown";
  private volatile long currentDartAttemptStartedElapsedMs;
  private long firstFrameForegroundRemainingMs = FLUTTER_FIRST_FRAME_DEADLINE_MS;
  private long foregroundStartedElapsedMs;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    StartupProcessClock.initialize();
    activityOnCreateElapsedMs = StartupProcessClock.elapsedSinceProcessStartMs();
    Log.i(STARTUP_TAG, "android_activity_on_create elapsedMs=" + activityOnCreateElapsedMs);
    initializeDartJniClassLoader();
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
    foregroundStartedElapsedMs = StartupProcessClock.processStartElapsedMs();
    armFlutterFirstFrameWatchdog();
  }

  /**
   * dart_jni 的 FFI class lookup 可在 Flutter 首帧前由传递依赖触发。该库的
   * JNIEnv/class loader 只会在 JniPlugin 的静态初始化中建立，因此必须在 Dart
   * executor 启动前显式加载；不能把它放进 post-first-frame 延迟插件组。
   */
  private void initializeDartJniClassLoader() {
    try {
      Class.forName("com.github.dart_lang.jni.JniPlugin");
      Log.i(STARTUP_TAG, "android_dart_jni_class_loader_initialized");
    } catch (ClassNotFoundException | LinkageError error) {
      Log.e(STARTUP_TAG, "android_dart_jni_class_loader_initialization_failed", error);
    }
  }

  @Override
  public void configureFlutterEngine(@NonNull FlutterEngine flutterEngine) {
    flutterEngineConfiguredElapsedMs = StartupProcessClock.elapsedSinceProcessStartMs();
    Log.i(
        STARTUP_TAG,
        "android_flutter_engine_configured elapsedMs="
            + flutterEngineConfiguredElapsedMs
            + startupAttemptLogSuffix());
    registerStartupTimingsChannel(flutterEngine);
    registerNativeRuntimeConfigChannel(flutterEngine);
    observeNativeFlutterFirstFrame(flutterEngine);
    // 由应用自有注册器明确装配启动必需插件；GeneratedPluginRegistrant 保持 Flutter
    // 原样生成且不参与此引擎装配，重插件继续由 StartupDeferredPluginRegistry 按需注册。
    StartupEagerPluginRegistry.registerWith(flutterEngine);
    IncomingCallNativeBridgePlugin.register(
        flutterEngine, getApplicationContext());
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
            "quwoquan/assistant/device_action")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) ->
                assistantDeviceActionPlugin().handle(call, result));
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            RUNTIME_CRASH_MARKER_CHANNEL)
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              if ("consumePreviousCrash".equals(call.method)) {
                result.success(consumePreviousNativeCrashMarker());
              } else if ("readPreviousAnr".equals(call.method)) {
                result.success(readPreviousNativeAnrMarker());
              } else if ("acknowledgePreviousAnr".equals(call.method)) {
                result.success(
                    acknowledgePreviousNativeAnrMarker(
                        call.argument("occurredAtEpochMs")));
              } else {
                result.notImplemented();
              }
            });
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/app_recovery")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              switch (call.method) {
                case "getRecoveryContext":
                  Map<String, Object> context = new HashMap<>();
                  context.put("platform", "android");
                  context.put("appVersion", BuildConfig.VERSION_NAME);
                  context.put("buildNumber", BuildConfig.VERSION_CODE);
                  context.put("osVersion", Build.VERSION.RELEASE);
                  context.put("deviceModel", Build.MANUFACTURER + " " + Build.MODEL);
                  context.put("recoveryBaseUrl", BuildConfig.QWQ_RECOVERY_BASE_URL);
                  context.put("publicWebUrl", BuildConfig.QWQ_PUBLIC_WEB_URL);
                  context.put(
                      "appDownloadBaseUrl",
                      BuildConfig.QWQ_APP_DOWNLOAD_BASE_URL);
                  result.success(context);
                  break;
                case "openTrustedExternalUrl":
                  result.success(openTrustedRecoveryUrl(stringArgument(call, "url")));
                  break;
                case "recordFatalStartup":
                  result.success(
                      recordCurrentDartAttemptFatal(
                          stringArgument(call, "attemptId"),
                          stringArgument(call, "failureCode")));
                  break;
                case "readPendingNativeStartupFatal":
                  result.success(readPendingNativeStartupFatal());
                  break;
                case "ackPendingNativeStartupFatal":
                  acknowledgePendingNativeStartupFatal();
                  result.success(null);
                  break;
                case "readRecoveryFailureQueue":
                  startupWatchdogExecutor.execute(
                      () -> {
                        String value = recoveryFailureEncryptedStore().read();
                        startupHandler.post(() -> result.success(value));
                      });
                  break;
                case "writeRecoveryFailureQueue":
                  String queue = stringArgument(call, "value");
                  startupWatchdogExecutor.execute(
                      () -> {
                        boolean written = recoveryFailureEncryptedStore().write(queue);
                        startupHandler.post(() -> result.success(written));
                      });
                  break;
                case "clearRecoveryFailureQueue":
                  startupWatchdogExecutor.execute(
                      () -> {
                        boolean cleared = recoveryFailureEncryptedStore().clear();
                        startupHandler.post(() -> result.success(cleared));
                      });
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

  private void registerNativeRuntimeConfigChannel(@NonNull FlutterEngine flutterEngine) {
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/runtime/config")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              if (!"readRuntimeConfig".equals(call.method)) {
                result.notImplemented();
                return;
              }
              Map<String, Object> values = new HashMap<>();
              try {
                JSONObject runtimeDefines =
                    new JSONObject(BuildConfig.QWQ_RUNTIME_DART_DEFINES_JSON);
                Iterator<String> names = runtimeDefines.keys();
                while (names.hasNext()) {
                  String name = names.next();
                  String value = runtimeDefines.optString(name, "");
                  if (!value.isEmpty()) {
                    values.put(name, value);
                  }
                }
              } catch (Exception ignored) {
                // Dart 侧会把空配置收敛为既有 runtime configuration failure。
              }
              if (!BuildConfig.QWQ_CONTENT_RELEASE_ID.isEmpty()) {
                values.put("contentReleaseId", BuildConfig.QWQ_CONTENT_RELEASE_ID);
              }
              if (!BuildConfig.QWQ_CONTENT_MANIFEST_DIGEST.isEmpty()) {
                values.put("contentManifestDigest", BuildConfig.QWQ_CONTENT_MANIFEST_DIGEST);
              }
              if (!BuildConfig.QWQ_CONTENT_READINESS_RECEIPT_DIGEST.isEmpty()) {
                values.put(
                    "contentReadinessReceiptDigest",
                    BuildConfig.QWQ_CONTENT_READINESS_RECEIPT_DIGEST);
              }
              if (!BuildConfig.QWQ_LAUNCH_TARGET.isEmpty()) {
                values.put("launchTarget", BuildConfig.QWQ_LAUNCH_TARGET);
              }
              if (!BuildConfig.QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST.isEmpty()) {
                values.put(
                    "effectiveLaunchManifestDigest",
                    BuildConfig.QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST);
              }
              result.success(values);
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

  private boolean openTrustedRecoveryUrl(String rawUrl) {
    return TrustedRecoveryUrls.open(this, rawUrl, STARTUP_TAG);
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

  private AssistantDeviceActionPlugin assistantDeviceActionPlugin() {
    if (assistantDeviceActionPlugin == null) {
      assistantDeviceActionPlugin = new AssistantDeviceActionPlugin(this);
    }
    return assistantDeviceActionPlugin;
  }

  private RecoveryFailureEncryptedStore recoveryFailureEncryptedStore() {
    if (recoveryFailureEncryptedStore == null) {
      recoveryFailureEncryptedStore = new RecoveryFailureEncryptedStore(getApplicationContext());
    }
    return recoveryFailureEncryptedStore;
  }

  private boolean markCurrentBuildFatal() {
    return StartupHealthStore.markCurrentArtifactFatal(this);
  }

  private boolean recordCurrentDartAttemptFatal(String attemptId, String failureCode) {
    String normalizedAttemptId = safeStartupIdentifier(attemptId);
    String normalizedFailureCode = safeStartupFailureCode(failureCode);
    if ("unknown".equals(normalizedAttemptId)
        || normalizedFailureCode.isEmpty()
        || !normalizedAttemptId.equals(currentDartAttemptId)) {
      Log.i(STARTUP_TAG, "startup_fatal_marker_ignored reason=attempt_mismatch");
      return false;
    }
    if (currentDartAttemptIsHotRestart) {
      Log.i(STARTUP_TAG, "startup_fatal_marker_ignored reason=hot_restart");
      return false;
    }
    if (startupSafeTerminalConfirmed) {
      Log.i(STARTUP_TAG, "startup_fatal_marker_ignored reason=safe_shell_reached");
      return false;
    }
    if (!markCurrentBuildFatal()) {
      Log.i(STARTUP_TAG, "startup_fatal_marker_ignored reason=artifact_mismatch");
      return false;
    }
    Log.i(STARTUP_TAG, "startup_fatal_marker_recorded");
    return true;
  }

  private void markCurrentBuildSafeShell() {
    StartupHealthStore.markCurrentArtifactSafeShell(this);
  }

  private Map<String, Object> consumePreviousNativeCrashMarker() {
    return StartupHealthStore.consumePreviousRuntimeCrash(this);
  }

  private Map<String, Object> readPendingNativeStartupFatal() {
    // Confirmed startup fatals are intercepted by StartupGateActivity before
    // a Flutter Engine exists, so MainActivity can never own this payload.
    return null;
  }

  private void acknowledgePendingNativeStartupFatal() {
    StartupHealthStore.acknowledgeCrashMarker(this);
  }

  private Map<String, Object> readPreviousNativeAnrMarker() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
      return null;
    }
    ActivityManager manager =
        (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
    if (manager == null) {
      return null;
    }
    long consumedTimestamp =
        getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
            .getLong(RUNTIME_ANR_CONSUMED_TIMESTAMP_KEY, 0L);
    long latestAnrTimestamp = 0L;
    try {
      List<ApplicationExitInfo> exits =
          manager.getHistoricalProcessExitReasons(getPackageName(), 0, 10);
      for (ApplicationExitInfo exit : exits) {
        if (exit.getReason() != ApplicationExitInfo.REASON_ANR) {
          continue;
        }
        latestAnrTimestamp = Math.max(latestAnrTimestamp, exit.getTimestamp());
      }
    } catch (RuntimeException ignored) {
      return null;
    }
    if (latestAnrTimestamp <= consumedTimestamp) {
      return null;
    }
    long ageMs = System.currentTimeMillis() - latestAnrTimestamp;
    if (ageMs < 0L || ageMs > RUNTIME_ANR_MAX_AGE_MS) {
      // 超出事件目录 TTL 的事实不再上报，但仍推进高水位，避免每次启动重复扫描。
      acknowledgePreviousNativeAnrMarker(latestAnrTimestamp);
      return null;
    }
    Map<String, Object> marker = new HashMap<>();
    marker.put("source", "android_application_exit_info");
    marker.put("occurredAtEpochMs", latestAnrTimestamp);
    return marker;
  }

  private boolean acknowledgePreviousNativeAnrMarker(Object rawTimestamp) {
    if (!(rawTimestamp instanceof Number)) {
      return false;
    }
    long occurredAtEpochMs = ((Number) rawTimestamp).longValue();
    if (occurredAtEpochMs <= 0L) {
      return false;
    }
    long consumedTimestamp =
        getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
            .getLong(RUNTIME_ANR_CONSUMED_TIMESTAMP_KEY, 0L);
    if (occurredAtEpochMs <= consumedTimestamp) {
      return true;
    }
    return getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
        .edit()
        .putLong(RUNTIME_ANR_CONSUMED_TIMESTAMP_KEY, occurredAtEpochMs)
        .commit();
  }

  private void registerStartupTimingsChannel(@NonNull FlutterEngine flutterEngine) {
    new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            "quwoquan/startup/timings")
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) -> {
              if ("beginStartupAttempt".equals(call.method)) {
                String attemptId = "";
                if (call.arguments instanceof Map) {
                  Object rawAttemptId = ((Map<?, ?>) call.arguments).get("attemptId");
                  if (rawAttemptId != null) {
                    attemptId = safeStartupIdentifier(rawAttemptId.toString());
                  }
                }
                if (attemptId.isEmpty() || "unknown".equals(attemptId)) {
                  result.error("invalid_startup_attempt", "attemptId is required", null);
                  return;
                }
                boolean hotRestart = dartStartupAttemptStarted;
                long nowElapsedMs = SystemClock.elapsedRealtime();
                dartStartupAttemptStarted = true;
                currentDartAttemptId = attemptId;
                currentDartAttemptIsHotRestart = hotRestart;
                currentDartAttemptStartedElapsedMs =
                    hotRestart ? nowElapsedMs : StartupProcessClock.processStartElapsedMs();
                Map<String, Object> payload = new HashMap<>();
                payload.put("androidActivityOnCreateMs", activityOnCreateElapsedMs);
                payload.put(
                    "androidFlutterEngineConfiguredMs", flutterEngineConfiguredElapsedMs);
                payload.put(
                    "elapsedSinceProcessStartMs",
                    StartupProcessClock.elapsedSinceProcessStartMs());
                payload.put(
                    "elapsedSinceAttemptStartMs",
                    Math.max(0L, nowElapsedMs - currentDartAttemptStartedElapsedMs));
                payload.put("attemptKind", hotRestart ? "hotRestart" : "cold");
                payload.put("deadlineOrigin", hotRestart ? "dartHotRestart" : "nativeProcess");
                payload.put("startupAttemptId", attemptId);
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
                  confirmStartupSafeTerminal(startupEventElapsedMs(event));
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

  private long startupEventElapsedMs(Object event) {
    if (!(event instanceof String)) {
      return -1L;
    }
    try {
      return new JSONObject((String) event).optLong("elapsedMs", -1L);
    } catch (Exception ignored) {
      return -1L;
    }
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
    if ("startup_attempt_started".equals(eventName)) {
      try {
        JSONObject payload = new JSONObject(event);
        String reportedAttemptId =
            safeStartupIdentifier(payload.optString("attemptId", ""));
        if (!reportedAttemptId.equals(currentDartAttemptId)) {
          Log.i(STARTUP_TAG, "android_dart_startup_attempt_invalid reason=attempt_mismatch");
          return;
        }
        currentLaunchMode = safeStartupIdentifier(payload.optString("launchMode", ""));
        String configurationState =
            safeStartupIdentifier(payload.optString("configurationState", "unknown"));
        String missingDefineKeys =
            safeDefineKeyList(payload.optString("missingDefineKeys", ""));
        Log.i(
            STARTUP_TAG,
            "android_dart_startup_attempt attemptId="
                + currentDartAttemptId
                + " launchMode="
                + currentLaunchMode
                + " hotRestart="
                + currentDartAttemptIsHotRestart
                + " configurationState="
                + configurationState
                + " effectiveLaunchManifestDigest="
                + BuildConfig.QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST
                + (missingDefineKeys.isEmpty() ? "" : " missingDefineKeys=" + missingDefineKeys));
      } catch (Exception ignored) {
        Log.i(STARTUP_TAG, "android_dart_startup_attempt_invalid");
      }
      return;
    }
    if ("startup_runtime_configured".equals(eventName)) {
      try {
        JSONObject payload = new JSONObject(event);
        currentLaunchMode = safeStartupIdentifier(payload.optString("launchMode", ""));
        String configurationState =
            safeStartupIdentifier(payload.optString("configurationState", "unknown"));
        Log.i(
            STARTUP_TAG,
            "android_runtime_configured launchMode="
                + currentLaunchMode
                + " configurationState="
                + configurationState
                + " effectiveLaunchManifestDigest="
                + BuildConfig.QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST);
      } catch (Exception ignored) {
        Log.i(STARTUP_TAG, "android_runtime_configured_invalid");
      }
      return;
    }
    if ("startup_bootstrap_failure".equals(eventName)) {
      // bootstrap 根已经显示 Flutter recovery；只输出稳定错误码，不转写异常或用户态上下文。
      String missingDefineKeys = "";
      try {
        missingDefineKeys = safeDefineKeyList(
            new JSONObject(event).optString("missingDefineKeys", ""));
      } catch (Exception ignored) {
        // 固定 bootstrap failure 标识仍需输出。
      }
      Log.i(
          STARTUP_TAG,
          "startup_probe phase=bootstrap_failure"
              + safeStartupFailureCodeSuffix(event)
              + (missingDefineKeys.isEmpty() ? "" : " missingDefineKeys=" + missingDefineKeys));
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

  private String safeStartupIdentifier(String value) {
    if (value == null || value.isEmpty() || value.length() > 128) {
      return "unknown";
    }
    for (int index = 0; index < value.length(); index++) {
      char character = value.charAt(index);
      if (!(Character.isLetterOrDigit(character) || character == '_' || character == '-')) {
        return "unknown";
      }
    }
    return value;
  }

  private String safeStartupFailureCode(String value) {
    if (value == null || value.isEmpty() || value.length() > 128) {
      return "";
    }
    for (int index = 0; index < value.length(); index++) {
      char character = value.charAt(index);
      if (!(Character.isLetterOrDigit(character)
          || character == '.'
          || character == '_'
          || character == '-')) {
        return "";
      }
    }
    return value;
  }

  private String safeDefineKeyList(String value) {
    if (value == null || value.isEmpty() || value.length() > 512) {
      return "";
    }
    for (int index = 0; index < value.length(); index++) {
      char character = value.charAt(index);
      if (!(Character.isLetterOrDigit(character) || character == '_' || character == ',')) {
        return "";
      }
    }
    return value;
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
    // 原生 watchdog 只守护 renderer 首帧。safe terminal 较慢交由 Flutter
    // 安全状态机处理，绝不能覆盖已经可见的 Flutter UI。
    boolean firstNativeFrame = !flutterFirstFrameConfirmed;
    if (firstNativeFrame) {
      flutterFirstFrameConfirmed = true;
      cancelFlutterFirstFrameWatchdog();
    }
    Log.i(
        STARTUP_TAG,
        "android_flutter_first_frame elapsedMs="
            + StartupProcessClock.elapsedSinceProcessStartMs()
            + " source="
            + source
            + startupAttemptLogSuffix());
  }

  private void confirmStartupSafeTerminal(long reportedElapsedMs) {
    // MethodChannel 可能比 watchdog 主线程任务晚几毫秒。只要 Flutter 已到
    // routerShell / recovery 安全面，就必须取消看门狗并撤销竞态恢复层。
    boolean firstNativeSafeTerminal = !startupSafeTerminalConfirmed;
    if (firstNativeSafeTerminal) {
      startupSafeTerminalConfirmed = true;
      markCurrentBuildSafeShell();
      cancelFlutterFirstFrameWatchdog();
    }
    long receivedElapsedMs = StartupProcessClock.elapsedSinceProcessStartMs();
    long reportedMs = reportedElapsedMs >= 0L ? reportedElapsedMs : receivedElapsedMs;
    long effectiveBoundaryMs = Math.max(reportedMs, receivedElapsedMs);
    if (flutterFirstFrameConfirmed && effectiveBoundaryMs > FLUTTER_FIRST_FRAME_DEADLINE_MS) {
      recordStartupSafeTerminalSlow(effectiveBoundaryMs);
    }
    Log.i(
        STARTUP_TAG,
        "android_startup_safe_terminal reportedElapsedMs="
            + reportedMs
            + " receivedMs="
            + receivedElapsedMs
            + startupAttemptLogSuffix());
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

  private void armFlutterFirstFrameWatchdog() {
    if (flutterFirstFrameConfirmed
        || startupSafeTerminalConfirmed
        || nativeFirstFrameDeadlineReached
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
        || nativeFirstFrameDeadlineReached
        || !appInForeground) {
      return;
    }
    final long elapsedMs = StartupProcessClock.elapsedSinceProcessStartMs();
    // 必须在主线程再次核对 renderer 首帧；后台任务与首帧回调竞争时，
    // 只要已有 Flutter UI，就绝不能显示 native recovery。
    startupHandler.post(
        () -> {
          if (flutterFirstFrameConfirmed
              || startupSafeTerminalConfirmed
              || nativeFirstFrameDeadlineReached
              || !appInForeground) {
            return;
          }
          nativeFirstFrameDeadlineReached = true;
          recordNativeStartupDeadline(elapsedMs, true);
        });
  }

  private void recordNativeStartupDeadline(long elapsedMs, boolean firstFrameMissing) {
    if (!firstFrameMissing) return;
    Log.w(
        STARTUP_TAG,
        "android_native_first_frame_timeout elapsedMs="
            + elapsedMs
            + startupAttemptLogSuffix());
    if (startupTelemetryJournal == null) {
      return;
    }
    startupTelemetryJournal.record(
        "performance",
        elapsedMs,
        "native_first_frame_timeout",
        "",
        "",
        "native_watchdog",
        "android_process");
  }

  @NonNull
  private String startupAttemptLogSuffix() {
    String attemptId =
        currentDartAttemptId.isEmpty()
            ? (startupTelemetryJournal == null ? "" : startupTelemetryJournal.attemptId())
            : currentDartAttemptId;
    if (attemptId.isEmpty()) {
      return "";
    }
    return " attemptId="
        + attemptId
        + (startupTelemetryJournal == null
            ? ""
            : " nativeAttemptId=" + startupTelemetryJournal.attemptId())
        + " launchMode="
        + currentLaunchMode;
  }

  @Override
  @SuppressWarnings("deprecation") // QQ OpenSDK still returns through startActivityForResult.
  protected void onActivityResult(int requestCode, int resultCode, Intent data) {
    if (commercialAuthPlugin != null
        && commercialAuthPlugin.onActivityResult(requestCode, resultCode, data)) {
      return;
    }
    super.onActivityResult(requestCode, resultCode, data);
  }

  @Override
  public void onRequestPermissionsResult(
      int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
    if (assistantDeviceActionPlugin != null
        && assistantDeviceActionPlugin.onRequestPermissionsResult(requestCode, grantResults)) {
      return;
    }
    super.onRequestPermissionsResult(requestCode, permissions, grantResults);
  }

  private String stringArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value == null ? "" : value.toString().trim();
  }

}
