package com.quwoquan.quwoquan_app;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
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
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.annotation.NonNull;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.engine.renderer.FlutterUiDisplayListener;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
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
  private static final long FLUTTER_FIRST_FRAME_DEADLINE_MS = 6000L;
  private static final long NATIVE_TERMINAL_RECONCILIATION_WINDOW_MS = 120L;
  private static final String NATIVE_RECOVERY_VIEW_TAG = "qwq_native_startup_recovery";
  private static final String RUNTIME_CRASH_MARKER_CHANNEL =
      "quwoquan/runtime/native_crash_marker";
  private static final String RUNTIME_CRASH_MARKER_PREFERENCES =
      "quwoquan.runtime.diagnostics";
  private static final String RUNTIME_CRASH_MARKER_KIND_KEY =
      "previous_native_crash_kind";
  private static final String RUNTIME_ANR_CONSUMED_TIMESTAMP_KEY =
      "previous_native_anr_consumed_timestamp";
  private static final String STARTUP_HEALTH_BUILD_KEY = "startup_health_build";
  private static final String STARTUP_HEALTH_SAFE_SHELL_KEY = "startup_health_safe_shell";
  private static final String STARTUP_HEALTH_FATAL_BUILD_KEY = "startup_health_fatal_build";
  private static final String STARTUP_HEALTH_FATAL_AT_KEY = "startup_health_fatal_at";
  private static final long RUNTIME_ANR_MAX_AGE_MS = TimeUnit.HOURS.toMillis(72);
  private static volatile boolean nativeCrashMarkerInstalled;
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
  private RecoveryFailureEncryptedStore recoveryFailureEncryptedStore;
  private ScheduledFuture<?> flutterFirstFrameWatchdog;
  private ScheduledFuture<?> nativeRecoveryTerminalReconciliation;
  private FlutterEngine startupFlutterEngine;
  private FlutterUiDisplayListener flutterUiDisplayListener;
  private volatile boolean flutterFirstFrameConfirmed;
  private volatile boolean startupSafeTerminalConfirmed;
  private volatile boolean appInForeground;
  private volatile boolean nativeRecoveryShown;
  private volatile boolean nativeRecoveryDeadlineReached;
  private volatile boolean confirmedPreviousBuildFatal;
  private volatile boolean recoveryExternalOpenInFlight;
  private volatile boolean recoveryVersionCheckInFlight;
  private volatile boolean recoveryVersionRefreshPending;
  private volatile boolean dartStartupAttemptStarted;
  private volatile String currentDartAttemptId = "";
  private volatile String currentLaunchMode = "unknown";
  private long firstFrameForegroundRemainingMs = FLUTTER_FIRST_FRAME_DEADLINE_MS;
  private long foregroundStartedElapsedMs;
  private TextView startupRecoveryTitle;
  private TextView startupRecoveryMessage;
  private Button startupRecoveryPrimary;
  private Button startupRecoveryWeb;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    installNativeCrashMarker();
    promoteConfirmedPlatformStartupCrash();
    confirmedPreviousBuildFatal = shouldRecoverConfirmedStartupFatal();
    markCurrentBuildStarting();
    activityOnCreateElapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
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
    foregroundStartedElapsedMs = processStartElapsedMs;
    if (confirmedPreviousBuildFatal) {
      startupSafeTerminalConfirmed = true;
      showNativeStartupRecovery();
    } else {
      armFlutterFirstFrameWatchdog();
    }
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
    flutterEngineConfiguredElapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
    Log.i(
        STARTUP_TAG,
        "android_flutter_engine_configured elapsedMs="
            + flutterEngineConfiguredElapsedMs
            + startupAttemptLogSuffix());
    registerStartupTimingsChannel(flutterEngine);
    observeNativeFlutterFirstFrame(flutterEngine);
    // Gradle 在构建期通过 patch_android_plugin_registrant.sh 从 generated registrant
    // 剥离首帧后基础组（SecureStorage/Prefs/设备与网络探测）和 feature-demand 组。
    // bootstrap 只能使用 native timing/journal bridge；基础组由 post-frame barrier 装配。
    super.configureFlutterEngine(flutterEngine);
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
                  result.success(context);
                  break;
                case "openTrustedExternalUrl":
                  result.success(openTrustedRecoveryUrl(stringArgument(call, "url")));
                  break;
                case "recordFatalStartup":
                  markCurrentBuildFatal();
                  result.success(null);
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
    try {
      Uri uri = Uri.parse(rawUrl == null ? "" : rawUrl.trim());
      if (!"https".equalsIgnoreCase(uri.getScheme())
          || uri.getHost() == null
          || uri.getHost().isEmpty()
          || uri.getUserInfo() != null
          || !isTrustedRecoveryHost(uri.getHost())) {
        return false;
      }
      Intent intent = new Intent(Intent.ACTION_VIEW, uri);
      intent.addCategory(Intent.CATEGORY_BROWSABLE);
      startActivity(intent);
      return true;
    } catch (RuntimeException error) {
      Log.w(STARTUP_TAG, "android_recovery_external_open_failed", error);
      return false;
    }
  }

  private boolean isTrustedRecoveryHost(String rawHost) {
    String host = rawHost.toLowerCase(java.util.Locale.ROOT);
    return host.equals("quwoquan.com")
        || host.endsWith(".quwoquan.com")
        || host.equals("quwoquan-env.test")
        || host.endsWith(".quwoquan-env.test");
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

  private RecoveryFailureEncryptedStore recoveryFailureEncryptedStore() {
    if (recoveryFailureEncryptedStore == null) {
      recoveryFailureEncryptedStore = new RecoveryFailureEncryptedStore(getApplicationContext());
    }
    return recoveryFailureEncryptedStore;
  }

  private void installNativeCrashMarker() {
    synchronized (MainActivity.class) {
      if (nativeCrashMarkerInstalled) {
        return;
      }
      nativeCrashMarkerInstalled = true;
      // 此处仅观察 Java 未捕获异常；信号级原生崩溃必须交由获批准的平台崩溃报告器，
      // 禁止在此通过不安全的 signal handler 截获。
      Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
      Thread.setDefaultUncaughtExceptionHandler(
          (thread, error) -> {
            persistPreviousNativeCrashMarker(error);
            if (previous != null) {
              previous.uncaughtException(thread, error);
              return;
            }
            ThreadGroup group = thread.getThreadGroup();
            if (group != null) {
              group.uncaughtException(thread, error);
              return;
            }
            android.os.Process.killProcess(android.os.Process.myPid());
            System.exit(10);
          });
    }
  }

  private boolean shouldRecoverConfirmedStartupFatal() {
    String fatalBuild =
        getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
            .getString(STARTUP_HEALTH_FATAL_BUILD_KEY, "");
    String currentBuild = String.valueOf(BuildConfig.VERSION_CODE);
    if (fatalBuild == null || fatalBuild.isEmpty()) {
      return false;
    }
    if (!currentBuild.equals(fatalBuild)) {
      getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
          .edit()
          .remove(STARTUP_HEALTH_FATAL_BUILD_KEY)
          .remove(STARTUP_HEALTH_FATAL_AT_KEY)
          .apply();
      return false;
    }
    return true;
  }

  private void promoteConfirmedPlatformStartupCrash() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
      return;
    }
    android.content.SharedPreferences preferences =
        getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE);
    String currentBuild = String.valueOf(BuildConfig.VERSION_CODE);
    String previousBuild = preferences.getString(STARTUP_HEALTH_BUILD_KEY, "");
    boolean previousSafeShell =
        preferences.getBoolean(STARTUP_HEALTH_SAFE_SHELL_KEY, true);
    if (!currentBuild.equals(previousBuild) || previousSafeShell) {
      return;
    }

    ActivityManager manager =
        (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
    if (manager == null) {
      return;
    }
    ApplicationExitInfo latestExit = null;
    try {
      for (ApplicationExitInfo exit :
          manager.getHistoricalProcessExitReasons(getPackageName(), 0, 5)) {
        if (latestExit == null || exit.getTimestamp() > latestExit.getTimestamp()) {
          latestExit = exit;
        }
      }
    } catch (RuntimeException ignored) {
      return;
    }
    if (latestExit == null) {
      return;
    }
    int reason = latestExit.getReason();
    if (reason != ApplicationExitInfo.REASON_CRASH
        && reason != ApplicationExitInfo.REASON_CRASH_NATIVE) {
      return;
    }
    String kind =
        reason == ApplicationExitInfo.REASON_CRASH_NATIVE
            ? "AndroidNativeCrash"
            : "AndroidProcessCrash";
    preferences
        .edit()
        .putString(STARTUP_HEALTH_FATAL_BUILD_KEY, currentBuild)
        .putLong(STARTUP_HEALTH_FATAL_AT_KEY, latestExit.getTimestamp())
        .putString(RUNTIME_CRASH_MARKER_KIND_KEY, kind)
        .commit();
  }

  private void markCurrentBuildStarting() {
    getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
        .edit()
        .putString(STARTUP_HEALTH_BUILD_KEY, String.valueOf(BuildConfig.VERSION_CODE))
        .putBoolean(STARTUP_HEALTH_SAFE_SHELL_KEY, false)
        .apply();
  }

  private void markCurrentBuildFatal() {
    getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
        .edit()
        .putString(STARTUP_HEALTH_FATAL_BUILD_KEY, String.valueOf(BuildConfig.VERSION_CODE))
        .putLong(STARTUP_HEALTH_FATAL_AT_KEY, System.currentTimeMillis())
        .commit();
  }

  private void markCurrentBuildSafeShell() {
    if (confirmedPreviousBuildFatal) {
      return;
    }
    getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
        .edit()
        .putString(STARTUP_HEALTH_BUILD_KEY, String.valueOf(BuildConfig.VERSION_CODE))
        .putBoolean(STARTUP_HEALTH_SAFE_SHELL_KEY, true)
        .remove(STARTUP_HEALTH_FATAL_BUILD_KEY)
        .remove(STARTUP_HEALTH_FATAL_AT_KEY)
        .apply();
  }

  private void persistPreviousNativeCrashMarker(Throwable error) {
    try {
      String kind = error == null ? "UnknownNativeError" : error.getClass().getSimpleName();
      if (kind == null || kind.trim().isEmpty()) {
        kind = "UnknownNativeError";
      }
      // 下次 Dart 启动只需要稳定类别；异常消息和堆栈可能含用户数据，绝不能持久化。
      kind = kind.replaceAll("[^A-Za-z0-9_.-]", "_");
      if (kind.length() > 80) {
        kind = kind.substring(0, 80);
      }
      getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
          .edit()
          .putString(RUNTIME_CRASH_MARKER_KIND_KEY, kind)
          .commit();
      boolean safeShell =
          getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
              .getBoolean(STARTUP_HEALTH_SAFE_SHELL_KEY, false);
      if (!safeShell) {
        markCurrentBuildFatal();
      }
    } catch (RuntimeException ignored) {
      // Never replace the platform's crash handling path with observability work.
    }
  }

  private Map<String, Object> consumePreviousNativeCrashMarker() {
    if (confirmedPreviousBuildFatal) {
      return null;
    }
    String kind =
        getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
            .getString(RUNTIME_CRASH_MARKER_KIND_KEY, "");
    if (kind == null || kind.trim().isEmpty()) {
      return null;
    }
    getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
        .edit()
        .remove(RUNTIME_CRASH_MARKER_KIND_KEY)
        .apply();
    Map<String, Object> marker = new HashMap<>();
    marker.put("kind", kind);
    return marker;
  }

  private Map<String, Object> readPendingNativeStartupFatal() {
    if (!confirmedPreviousBuildFatal) {
      return null;
    }
    android.content.SharedPreferences preferences =
        getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE);
    String kind = preferences.getString(RUNTIME_CRASH_MARKER_KIND_KEY, "");
    long occurredAtMs = preferences.getLong(STARTUP_HEALTH_FATAL_AT_KEY, 0L);
    if (kind == null || kind.trim().isEmpty() || occurredAtMs <= 0L) {
      return null;
    }
    SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
    formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
    Map<String, Object> marker = new HashMap<>();
    marker.put("errorType", kind);
    marker.put("occurredAt", formatter.format(new Date(occurredAtMs)));
    return marker;
  }

  private void acknowledgePendingNativeStartupFatal() {
    getSharedPreferences(RUNTIME_CRASH_MARKER_PREFERENCES, MODE_PRIVATE)
        .edit()
        .remove(RUNTIME_CRASH_MARKER_KIND_KEY)
        .apply();
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
    if (recoveryVersionRefreshPending
        && nativeRecoveryShown
        && startupRecoveryTitle != null
        && startupRecoveryMessage != null
        && startupRecoveryPrimary != null
        && startupRecoveryWeb != null) {
      recoveryVersionRefreshPending = false;
      checkNativeRecoveryVersion(
          startupRecoveryTitle,
          startupRecoveryMessage,
          startupRecoveryPrimary,
          startupRecoveryWeb);
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
    startupRecoveryTitle = null;
    startupRecoveryMessage = null;
    startupRecoveryPrimary = null;
    startupRecoveryWeb = null;
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
        currentDartAttemptId =
            safeStartupIdentifier(payload.optString("attemptId", ""));
        currentLaunchMode = safeStartupIdentifier(payload.optString("launchMode", ""));
        boolean hotRestart = dartStartupAttemptStarted;
        dartStartupAttemptStarted = true;
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
                + hotRestart
                + " configurationState="
                + configurationState
                + (missingDefineKeys.isEmpty() ? "" : " missingDefineKeys=" + missingDefineKeys));
      } catch (Exception ignored) {
        Log.i(STARTUP_TAG, "android_dart_startup_attempt_invalid");
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
      dismissNativeStartupRecoveryAfterFlutterFirstFrame();
    }
    Log.i(
        STARTUP_TAG,
        "android_flutter_first_frame elapsedMs="
            + (SystemClock.elapsedRealtime() - processStartElapsedMs)
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
      cancelNativeRecoveryTerminalReconciliation();
      dismissNativeStartupRecoveryForSafeTerminalRace();
    }
    long receivedElapsedMs = SystemClock.elapsedRealtime() - processStartElapsedMs;
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

  private void showNativeStartupRecovery() {
    if ((flutterFirstFrameConfirmed && !confirmedPreviousBuildFatal)
        || (startupSafeTerminalConfirmed && !confirmedPreviousBuildFatal)
        || nativeRecoveryShown
        || isFinishing()
        || isDestroyed()) {
      return;
    }
    nativeRecoveryShown = true;

    ViewGroup root = (ViewGroup) getWindow().getDecorView();
    if (root.findViewWithTag(NATIVE_RECOVERY_VIEW_TAG) != null) {
      return;
    }
    final int backgroundColor = Color.rgb(247, 247, 252);
    getWindow().setStatusBarColor(backgroundColor);
    getWindow().setNavigationBarColor(backgroundColor);
    getWindow()
        .getDecorView()
        .setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);

    FrameLayout recovery = new FrameLayout(this);
    recovery.setTag(NATIVE_RECOVERY_VIEW_TAG);
    recovery.setBackgroundColor(backgroundColor);

    LinearLayout content = new LinearLayout(this);
    content.setOrientation(LinearLayout.VERTICAL);
    content.setGravity(Gravity.CENTER_HORIZONTAL);
    content.setPadding(dp(24), 0, dp(24), 0);
    content.setTranslationY(getResources().getDisplayMetrics().heightPixels * 0.05f);

    TextView title = new TextView(this);
    title.setText("应用暂时无法启动");
    title.setTextColor(Color.rgb(17, 19, 24));
    title.setTextSize(28);
    title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
    title.setGravity(Gravity.CENTER);
    content.addView(
        title,
        new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(44)));

    TextView message = new TextView(this);
    message.setText("正在检查可用版本");
    message.setTextColor(Color.rgb(107, 112, 124));
    message.setTextSize(17);
    message.setGravity(Gravity.CENTER);
    LinearLayout.LayoutParams messageLayout =
        new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52));
    messageLayout.topMargin = dp(16);
    content.addView(message, messageLayout);

    Button primary = new Button(this);
    configureRecoveryButton(primary, "正在检查…", true, false);
    LinearLayout.LayoutParams primaryLayout =
        new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
    primaryLayout.topMargin = dp(28);
    content.addView(primary, primaryLayout);

    Button web = new Button(this);
    configureRecoveryButton(web, "使用网页版", false, true);
    web.setOnClickListener(
        ignored -> openRecoveryTarget(BuildConfig.QWQ_PUBLIC_WEB_URL, "", "网页暂时无法打开，请稍后再试"));
    LinearLayout.LayoutParams webLayout =
        new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
    webLayout.topMargin = dp(12);
    content.addView(web, webLayout);

    FrameLayout.LayoutParams contentLayout =
        new FrameLayout.LayoutParams(dp(328), ViewGroup.LayoutParams.WRAP_CONTENT);
    contentLayout.gravity = Gravity.CENTER;
    recovery.addView(content, contentLayout);
    root.addView(
        recovery,
        new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    startupRecoveryTitle = title;
    startupRecoveryMessage = message;
    startupRecoveryPrimary = primary;
    startupRecoveryWeb = web;
    checkNativeRecoveryVersion(title, message, primary, web);
  }

  private void checkNativeRecoveryVersion(
      TextView title, TextView message, Button primary, Button web) {
    if (recoveryVersionCheckInFlight) {
      return;
    }
    recoveryVersionCheckInFlight = true;
    startupWatchdogExecutor.execute(
        () -> {
          HttpURLConnection connection = null;
          try {
            String base = BuildConfig.QWQ_RECOVERY_BASE_URL.replaceAll("/+$", "");
            URL endpoint =
                new URL(
                    base
                        + "/ops/app-recovery/version?platform=android&appVersion="
                        + URLEncoder.encode(BuildConfig.VERSION_NAME, StandardCharsets.UTF_8.name())
                        + "&buildNumber="
                        + BuildConfig.VERSION_CODE);
            connection = (HttpURLConnection) endpoint.openConnection();
            connection.setConnectTimeout(1500);
            connection.setReadTimeout(1500);
            connection.setRequestMethod("GET");
            connection.setRequestProperty("Accept", "application/json");
            connection.setUseCaches(false);
            if (connection.getResponseCode() < 200 || connection.getResponseCode() >= 300) {
              throw new IllegalStateException("version service unavailable");
            }
            JSONObject payload = new JSONObject(readLimitedResponse(connection));
            if (payload.length() != 4) {
              throw new IllegalStateException("version response field mismatch");
            }
            int latestBuild = Integer.parseInt(payload.getString("latestBuild"));
            String updateUrl = payload.getString("updateUrl");
            String recoveryUrl = payload.getString("recoveryUrl");
            if (!isTrustedRecoveryUrl(updateUrl) || !isTrustedRecoveryUrl(recoveryUrl)) {
              throw new IllegalStateException("version response url rejected");
            }
            startupHandler.post(
                () -> {
                  if (latestBuild > BuildConfig.VERSION_CODE) {
                    title.setText("当前版本需要更新");
                    message.setText("更新后即可正常启动");
                    configureRecoveryButton(primary, "前往更新", true, true);
                    primary.setOnClickListener(
                        ignored ->
                            openRecoveryTarget(
                                updateUrl,
                                recoveryUrl,
                                "暂时无法打开更新页面，请稍后再试",
                                true));
                    web.setVisibility(View.VISIBLE);
                    return;
                  }
                  title.setText("当前已是最新版本");
                  message.setText("请使用网页版继续");
                  configureRecoveryButton(primary, "使用网页版", true, true);
                  primary.setOnClickListener(
                      ignored ->
                          openRecoveryTarget(
                              BuildConfig.QWQ_PUBLIC_WEB_URL,
                              recoveryUrl,
                              "网页暂时无法打开，请稍后再试"));
                  web.setVisibility(View.GONE);
                });
          } catch (Exception ignored) {
            startupHandler.post(
                () -> {
                  title.setText("应用暂时无法启动");
                  message.setText("请使用网页版继续");
                  configureRecoveryButton(primary, "使用网页版", true, true);
                  primary.setOnClickListener(
                      view ->
                          openRecoveryTarget(
                              BuildConfig.QWQ_PUBLIC_WEB_URL,
                              "",
                              "网页暂时无法打开，请稍后再试"));
                  web.setVisibility(View.GONE);
                });
          } finally {
            recoveryVersionCheckInFlight = false;
            if (connection != null) {
              connection.disconnect();
            }
          }
        });
  }

  private String readLimitedResponse(HttpURLConnection connection) throws Exception {
    try (InputStream input = connection.getInputStream();
        ByteArrayOutputStream output = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[4096];
      int read;
      while ((read = input.read(buffer)) >= 0) {
        if (output.size() + read > 65536) {
          throw new IllegalStateException("version response too large");
        }
        output.write(buffer, 0, read);
      }
      return output.toString(StandardCharsets.UTF_8.name());
    }
  }

  private void configureRecoveryButton(
      Button button, String label, boolean filled, boolean enabled) {
    button.setText(label);
    button.setTextSize(17);
    button.setAllCaps(false);
    button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
    button.setEnabled(enabled);
    button.setTextColor(
        enabled ? (filled ? Color.WHITE : Color.rgb(8, 123, 255)) : Color.rgb(107, 112, 124));
    GradientDrawable background = new GradientDrawable();
    background.setCornerRadius(dp(24));
    if (filled) {
      background.setColor(enabled ? Color.rgb(8, 123, 255) : Color.rgb(233, 237, 245));
    } else {
      background.setColor(Color.TRANSPARENT);
      background.setStroke(dp(1), Color.rgb(8, 123, 255));
    }
    button.setBackground(background);
  }

  private void openRecoveryTarget(String target, String fallback, String failureMessage) {
    openRecoveryTarget(target, fallback, failureMessage, false);
  }

  private void openRecoveryTarget(
      String target, String fallback, String failureMessage, boolean recheckVersionOnReturn) {
    if (recoveryExternalOpenInFlight) {
      return;
    }
    recoveryExternalOpenInFlight = true;
    boolean opened = openTrustedRecoveryUrl(target);
    if (!opened && fallback != null && !fallback.isEmpty()) {
      opened = openTrustedRecoveryUrl(fallback);
    }
    if (!opened) {
      Toast.makeText(this, failureMessage, Toast.LENGTH_SHORT).show();
    } else if (recheckVersionOnReturn) {
      recoveryVersionRefreshPending = true;
    }
    recoveryExternalOpenInFlight = false;
  }

  private boolean isTrustedRecoveryUrl(String rawUrl) {
    try {
      Uri uri = Uri.parse(rawUrl == null ? "" : rawUrl.trim());
      return "https".equalsIgnoreCase(uri.getScheme())
          && uri.getHost() != null
          && !uri.getHost().isEmpty()
          && uri.getUserInfo() == null
          && isTrustedRecoveryHost(uri.getHost());
    } catch (RuntimeException ignored) {
      return false;
    }
  }

  private int dp(int value) {
    return Math.round(value * getResources().getDisplayMetrics().density);
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
