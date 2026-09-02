package com.quwoquan.quwoquan_app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Predicate;

final class NativeRecoveryVersionResponse {
  private static final Set<String> CANONICAL_FIELDS =
      Set.of(
          "platform",
          "latestVersion",
          "latestBuild",
          "minimumSupportedVersion",
          "minimumSupportedBuild",
          "updateState",
          "updateUrl",
          "recoveryUrl");

  enum UpdateState {
    NONE("none"),
    AVAILABLE("available"),
    REQUIRED("required");

    final String wireName;

    UpdateState(String wireName) {
      this.wireName = wireName;
    }

    static UpdateState fromWire(String raw) {
      for (UpdateState value : values()) {
        if (value.wireName.equals(raw)) {
          return value;
        }
      }
      throw new IllegalArgumentException("unknown update state");
    }
  }

  final String platform;
  final String latestVersion;
  final long latestBuild;
  final String minimumSupportedVersion;
  final long minimumSupportedBuild;
  final UpdateState updateState;
  final String updateUrl;
  final String recoveryUrl;

  private NativeRecoveryVersionResponse(
      String platform,
      String latestVersion,
      long latestBuild,
      String minimumSupportedVersion,
      long minimumSupportedBuild,
      UpdateState updateState,
      String updateUrl,
      String recoveryUrl) {
    this.platform = platform;
    this.latestVersion = latestVersion;
    this.latestBuild = latestBuild;
    this.minimumSupportedVersion = minimumSupportedVersion;
    this.minimumSupportedBuild = minimumSupportedBuild;
    this.updateState = updateState;
    this.updateUrl = updateUrl;
    this.recoveryUrl = recoveryUrl;
  }

  boolean offersNativeUpdate() {
    return updateState != UpdateState.NONE && updateUrl != null;
  }

  static NativeRecoveryVersionResponse parse(
      String responseBody,
      String expectedPlatform,
      long currentBuild,
      Predicate<String> isTrustedUrl) {
    JsonElement root = JsonParser.parseString(responseBody);
    if (!root.isJsonObject() || currentBuild <= 0 || isTrustedUrl == null) {
      throw new IllegalArgumentException("invalid version response root");
    }
    JsonObject payload = root.getAsJsonObject();
    if (!payload.keySet().equals(CANONICAL_FIELDS)) {
      throw new IllegalArgumentException("version response field mismatch");
    }
    String platform = requiredString(payload, "platform");
    if (!platform.equals(expectedPlatform)) {
      throw new IllegalArgumentException("version response platform mismatch");
    }
    String latestVersion = requiredString(payload, "latestVersion");
    long latestBuild = positiveDecimal(payload, "latestBuild");
    String minimumSupportedVersion = requiredString(payload, "minimumSupportedVersion");
    long minimumSupportedBuild = positiveDecimal(payload, "minimumSupportedBuild");
    if (minimumSupportedBuild > latestBuild) {
      throw new IllegalArgumentException("version response minimum exceeds latest");
    }
    UpdateState updateState = UpdateState.fromWire(requiredString(payload, "updateState"));
    UpdateState expectedUpdateState =
        currentBuild < minimumSupportedBuild
            ? UpdateState.REQUIRED
            : currentBuild < latestBuild ? UpdateState.AVAILABLE : UpdateState.NONE;
    if (updateState != expectedUpdateState) {
      throw new IllegalArgumentException("version response update state mismatch");
    }
    String recoveryUrl = requiredString(payload, "recoveryUrl");
    if (!isTrustedUrl.test(recoveryUrl)) {
      throw new IllegalArgumentException("version response recovery URL rejected");
    }

    JsonElement rawUpdateUrl = payload.get("updateUrl");
    String updateUrl;
    if ("android".equals(expectedPlatform)) {
      updateUrl = requiredString(payload, "updateUrl");
      if (!isTrustedUrl.test(updateUrl)) {
        throw new IllegalArgumentException("version response update URL rejected");
      }
    } else if ("ios".equals(expectedPlatform) && rawUpdateUrl.isJsonNull()) {
      updateUrl = null;
    } else {
      throw new IllegalArgumentException("version response update URL mismatch");
    }
    return new NativeRecoveryVersionResponse(
        platform,
        latestVersion,
        latestBuild,
        minimumSupportedVersion,
        minimumSupportedBuild,
        updateState,
        updateUrl,
        recoveryUrl);
  }

  private static String requiredString(JsonObject payload, String field) {
    JsonElement value = payload.get(field);
    if (value == null
        || !value.isJsonPrimitive()
        || !value.getAsJsonPrimitive().isString()
        || value.getAsString().trim().isEmpty()) {
      throw new IllegalArgumentException("version response string invalid: " + field);
    }
    return value.getAsString().trim();
  }

  private static long positiveDecimal(JsonObject payload, String field) {
    String raw = requiredString(payload, field);
    if (!raw.matches("^[1-9][0-9]*$")) {
      throw new IllegalArgumentException("version response decimal invalid: " + field);
    }
    try {
      long value = Long.parseLong(raw);
      if (value <= 0) {
        throw new IllegalArgumentException("version response decimal invalid: " + field);
      }
      return value;
    } catch (NumberFormatException error) {
      throw new IllegalArgumentException("version response decimal invalid: " + field, error);
    }
  }
}

/**
 * Flutter Engine 之前的唯一 Android 启动 gate。
 *
 * <p>正常分支只进入 MainActivity；确认的同制品启动致命异常直接停留在原生恢复页。
 */
public final class StartupGateActivity extends Activity {
  private static final String STARTUP_TAG = "QWQStartup";
  static final String EXTRA_GATE_PASSED = "quwoquan.startup.GATE_PASSED";
  private static final String STATE_MAIN_HANDOFF_STARTED =
      "quwoquan.startup.MAIN_HANDOFF_STARTED";

  private final Handler mainHandler = new Handler(Looper.getMainLooper());
  private final ExecutorService versionExecutor =
      Executors.newSingleThreadExecutor(
          runnable -> {
            Thread thread = new Thread(runnable, "qwq-native-recovery-version");
            thread.setDaemon(true);
            return thread;
          });
  private volatile boolean recoveryVersionCheckInFlight;
  private boolean recoveryVersionRefreshPending;
  private boolean recoveryExternalOpenInFlight;
  private RuntimeConfigPackageStore runtimeConfigPackageStore;
  private RuntimeConfigActivationCoordinator runtimeConfigActivationCoordinator;
  private TextView recoveryTitle;
  private TextView recoveryMessage;
  private Button recoveryPrimary;
  private Button recoveryWeb;
  private boolean mainHandoffStarted;
  private boolean normalLaunchHandoffArmed;
  private boolean normalLaunchSurfaceReady;
  private boolean normalWindowFocusConfirmed;
  private boolean normalWindowFocusConfirmationDispatched;
  private boolean normalWindowFocusReleaseRequested;
  private boolean normalWindowFocusReleased;
  private boolean normalHandoffDispatchPosted;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    StartupProcessClock.initialize();
    super.onCreate(savedInstanceState);
    runtimeConfigPackageStore = AndroidRuntimeConfig.createStore(this);
    runtimeConfigActivationCoordinator =
        new RuntimeConfigActivationCoordinator(
            getApplicationContext().getNoBackupFilesDir(), runtimeConfigPackageStore);
    mainHandoffStarted =
        savedInstanceState != null
            && savedInstanceState.getBoolean(STATE_MAIN_HANDOFF_STARTED, false);
    if (mainHandoffStarted) {
      // The Main handoff was already committed before a configuration/process
      // recreation. Finishing this transient gate prevents a second handoff.
      finish();
      return;
    }
    RuntimeConfigActivationCoordinator.ConsumeResult activation =
        runtimeConfigActivationCoordinator.consumePendingRequest(getIntent(), isTaskRoot());
    if (activation.kind == RuntimeConfigActivationCoordinator.ConsumeKind.FAILED) {
      Log.e(
          STARTUP_TAG,
          "android_runtime_config_activation_failed code="
              + activation.errorCode
              + " issues="
              + String.join(",", activation.validationIssues));
      showNativeStartupRecovery();
      return;
    }
    if (activation.kind == RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED) {
      Log.i(STARTUP_TAG, "android_runtime_config_activation_complete");
      // Canonical executor 用第二次无 activation extra 的冷启动进入 Flutter。
      // 此进程只负责原生 CAS 与回执，成功后不得继续创建 Flutter engine。
      finishAndRemoveTask();
      return;
    }
    // 嵌入默认供给（embedded_default_package）已退役：缺 canonical supply 时由
    // 既有 typed trust/config 阻断在 Flutter 侧 fail-closed，此处不再补供给。
    StartupHealthStore.promoteConfirmedPlatformStartupCrash(this);
    if (!StartupHealthStore.shouldRecoverConfirmedStartupFatal(this)) {
      if (!isTaskRoot()) {
        // Repeated launcher taps and restored tasks must reuse the existing
        // MainActivity. Do not replay the native static frame or reopen a
        // startup-health attempt for an already-running task.
        Log.i(STARTUP_TAG, "android_gate_warm_task_handoff");
        startFlutterMainActivity();
        return;
      }
      StartupHealthStore.markCurrentArtifactStarting(this);
      showNativeLaunchFrameThenStartFlutter();
      return;
    }
    Log.w(STARTUP_TAG, "android_native_startup_gate_recovery");
    if (!StartupHealthStore.enqueueConfirmedStartupFatal(this)) {
      Log.w(STARTUP_TAG, "android_native_startup_failure_queue_write_failed");
    }
    showNativeStartupRecovery();
  }

  @Override
  protected void onResume() {
    super.onResume();
    if (recoveryVersionRefreshPending
        && recoveryTitle != null
        && recoveryMessage != null
        && recoveryPrimary != null
        && recoveryWeb != null) {
      recoveryVersionRefreshPending = false;
      checkNativeRecoveryVersion(
          recoveryTitle, recoveryMessage, recoveryPrimary, recoveryWeb);
    }
  }

  @Override
  public void onWindowFocusChanged(boolean hasFocus) {
    super.onWindowFocusChanged(hasFocus);
    if (!normalLaunchHandoffArmed) {
      return;
    }
    if (hasFocus) {
      if (normalWindowFocusConfirmed) {
        return;
      }
      normalWindowFocusConfirmed = true;
      // Wait for this callback to return before changing the native window's
      // focusability. Otherwise the focus-enter event itself can remain
      // unacknowledged while Flutter occupies the process main thread.
      mainHandler.post(
          () -> {
            if (isFinishing() || isDestroyed() || mainHandoffStarted) {
              return;
            }
            normalWindowFocusConfirmationDispatched = true;
            Log.i(STARTUP_TAG, "android_gate_window_focus_confirmed");
            requestWindowFocusReleaseWhenReady();
          });
      return;
    }
    if (!normalWindowFocusReleaseRequested || normalWindowFocusReleased) {
      return;
    }
    normalWindowFocusReleased = true;
    scheduleFlutterMainHandoffWhenReady();
  }

  @Override
  protected void onDestroy() {
    mainHandler.removeCallbacksAndMessages(null);
    recoveryTitle = null;
    recoveryMessage = null;
    recoveryPrimary = null;
    recoveryWeb = null;
    versionExecutor.shutdownNow();
    super.onDestroy();
  }

  private void startFlutterMainActivity() {
    if (mainHandoffStarted || isFinishing()) {
      return;
    }
    mainHandoffStarted = true;
    Intent incoming = getIntent();
    Intent main = new Intent(this, MainActivity.class);
    main.setAction(incoming.getAction());
    main.setData(incoming.getData());
    main.putExtras(incoming);
    main.putExtra(EXTRA_GATE_PASSED, true);
    main.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    if (incoming.getCategories() != null) {
      for (String category : incoming.getCategories()) {
        main.addCategory(category);
      }
    }
    Log.i(STARTUP_TAG, "android_gate_main_handoff");
    startActivity(main);
    suppressFlutterHandoffTransition();
    finish();
  }

  private void showNativeLaunchFrameThenStartFlutter() {
    normalLaunchHandoffArmed = true;
    normalLaunchSurfaceReady = false;
    final FrameLayout staticFrame = new FrameLayout(this);
    staticFrame.setBackgroundResource(R.drawable.launch_background);
    setContentView(staticFrame);
    ViewTreeObserver.OnDrawListener startAfterFirstDraw =
        new ViewTreeObserver.OnDrawListener() {
          @Override
          public void onDraw() {
            if (normalLaunchSurfaceReady) {
              return;
            }
            normalLaunchSurfaceReady = true;
            Log.i(STARTUP_TAG, "android_gate_static_frame_drawn");
            // ViewTreeObserver forbids listener removal during its own
            // dispatch. Post cleanup and the Main handoff so this first
            // static frame can complete without crashing Android 12+.
            mainHandler.post(
                () -> {
                  if (staticFrame.getViewTreeObserver().isAlive()) {
                    staticFrame.getViewTreeObserver().removeOnDrawListener(this);
                  }
                  requestWindowFocusReleaseWhenReady();
                });
          }
        };
    staticFrame.getViewTreeObserver().addOnDrawListener(startAfterFirstDraw);
    // A vendor compositor must not be able to trap startup indefinitely by
    // suppressing OnDraw. The fallback still leaves the static resource as the
    // only native brand surface and never creates a Flutter Engine in Gate.
    mainHandler.postDelayed(
        () -> {
          if (!normalLaunchSurfaceReady) {
            normalLaunchSurfaceReady = true;
            if (staticFrame.getViewTreeObserver().isAlive()) {
              staticFrame.getViewTreeObserver().removeOnDrawListener(startAfterFirstDraw);
            }
            Log.w(STARTUP_TAG, "android_gate_static_frame_draw_timeout");
            requestWindowFocusReleaseWhenReady();
          }
        },
        500L);
  }

  private void requestWindowFocusReleaseWhenReady() {
    if (!normalLaunchHandoffArmed
        || !normalLaunchSurfaceReady
        || !normalWindowFocusConfirmationDispatched
        || normalWindowFocusReleaseRequested
        || mainHandoffStarted
        || isFinishing()) {
      return;
    }
    normalWindowFocusReleaseRequested = true;
    // MainActivity's fresh Flutter initialization can block this process for
    // longer than Android's input timeout. Release and acknowledge the native
    // Gate's focus before starting Main so neither focus-enter nor focus-exit
    // events are left queued behind Flutter engine startup.
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE);
  }

  private void scheduleFlutterMainHandoffWhenReady() {
    if (!normalWindowFocusReleased
        || normalHandoffDispatchPosted
        || mainHandoffStarted
        || isFinishing()) {
      return;
    }
    normalHandoffDispatchPosted = true;
    // Starting Flutter can synchronously occupy this process' main thread for
    // several seconds on a fresh install. Dispatching from the next main-loop
    // message guarantees onWindowFocusChanged(false) has returned first, so
    // both native Gate FocusEvents are acknowledged before Flutter startup.
    mainHandler.post(
        () -> {
          if (!isFinishing() && !isDestroyed()) {
            Log.i(STARTUP_TAG, "android_gate_window_focus_released");
            startFlutterMainActivity();
          }
        });
  }

  @Override
  protected void onSaveInstanceState(Bundle outState) {
    outState.putBoolean(STATE_MAIN_HANDOFF_STARTED, mainHandoffStarted);
    super.onSaveInstanceState(outState);
  }

  @SuppressWarnings("deprecation")
  private void suppressFlutterHandoffTransition() {
    if (Build.VERSION.SDK_INT >= 34) {
      overrideActivityTransition(OVERRIDE_TRANSITION_OPEN, 0, 0);
      return;
    }
    overridePendingTransition(0, 0);
  }

  private void showNativeStartupRecovery() {
    final int backgroundColor = Color.rgb(247, 247, 252);
    styleNativeRecoverySystemBars(backgroundColor);

    FrameLayout recovery = new FrameLayout(this);
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
        ignored ->
            openRecoveryTarget(
                recoveryRuntimeValue("publicWebBaseUrl"),
                "",
                "网页暂时无法打开，请稍后再试"));
    LinearLayout.LayoutParams webLayout =
        new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
    webLayout.topMargin = dp(12);
    content.addView(web, webLayout);

    FrameLayout.LayoutParams contentLayout =
        new FrameLayout.LayoutParams(dp(328), ViewGroup.LayoutParams.WRAP_CONTENT);
    contentLayout.gravity = Gravity.CENTER;
    recovery.addView(content, contentLayout);
    setContentView(recovery);
    recoveryTitle = title;
    recoveryMessage = message;
    recoveryPrimary = primary;
    recoveryWeb = web;
    checkNativeRecoveryVersion(title, message, primary, web);
  }

  private void styleNativeRecoverySystemBars(int backgroundColor) {
    getWindow().getDecorView().setBackgroundColor(backgroundColor);
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
      WindowInsetsController controller = getWindow().getInsetsController();
      if (controller != null) {
        controller.setSystemBarsAppearance(
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
      }
    }
    applyVersionSpecificNativeRecoverySystemBarStyle(backgroundColor);
  }

  @SuppressWarnings("deprecation")
  private void applyVersionSpecificNativeRecoverySystemBarStyle(int backgroundColor) {
    if (Build.VERSION.SDK_INT < 35) {
      getWindow().setStatusBarColor(backgroundColor);
      getWindow().setNavigationBarColor(backgroundColor);
    }
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
      getWindow()
          .getDecorView()
          .setSystemUiVisibility(
              View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                  | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
    }
  }

  private void checkNativeRecoveryVersion(
      TextView title, TextView message, Button primary, Button web) {
    if (recoveryVersionCheckInFlight) {
      return;
    }
    recoveryVersionCheckInFlight = true;
    versionExecutor.execute(
        () -> {
          HttpURLConnection connection = null;
          try {
            java.util.Map<String, String> recoveryRuntime =
                runtimeConfigPackageStore.readRecoveryRuntimeValues();
            String base = recoveryRuntime.get("gatewayBaseUrl").replaceAll("/+$", "");
            if (!TrustedRecoveryUrls.isTrusted(base, recoveryRuntime)) {
              throw new IllegalStateException("recovery base URL rejected");
            }
            URL endpoint =
                new URL(
                    base
                        + "/ops/app-recovery/version?platform=android&appVersion="
                        + URLEncoder.encode(
                            BuildConfig.VERSION_NAME, StandardCharsets.UTF_8.name())
                        + "&buildNumber="
                        + BuildConfig.VERSION_CODE);
            connection = (HttpURLConnection) endpoint.openConnection();
            connection.setConnectTimeout(1500);
            connection.setReadTimeout(1500);
            connection.setRequestMethod("GET");
            connection.setRequestProperty("Accept", "application/json");
            connection.setUseCaches(false);
            if (connection.getResponseCode() < 200
                || connection.getResponseCode() >= 300) {
              throw new IllegalStateException("version service unavailable");
            }
            NativeRecoveryVersionResponse version =
                NativeRecoveryVersionResponse.parse(
                    readLimitedResponse(connection),
                    "android",
                    BuildConfig.VERSION_CODE,
                    rawUrl -> TrustedRecoveryUrls.isTrusted(rawUrl, recoveryRuntime));
            mainHandler.post(
                () -> {
                  if (!canUpdateRecoveryUi()) {
                    return;
                  }
                  if (version.offersNativeUpdate()) {
                    title.setText("当前版本需要更新");
                    message.setText("更新后即可正常启动");
                    configureRecoveryButton(primary, "前往更新", true, true);
                    primary.setOnClickListener(
                        ignored ->
                            openRecoveryTarget(
                                version.updateUrl,
                                version.recoveryUrl,
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
                              recoveryRuntime.get("publicWebBaseUrl"),
                              version.recoveryUrl,
                              "网页暂时无法打开，请稍后再试"));
                  web.setVisibility(View.GONE);
                });
          } catch (Exception ignored) {
            mainHandler.post(
                () -> {
                  if (!canUpdateRecoveryUi()) {
                    return;
                  }
                  title.setText("应用暂时无法启动");
                  message.setText("请使用网页版继续");
                  configureRecoveryButton(primary, "使用网页版", true, true);
                  primary.setOnClickListener(
                      view ->
                          openRecoveryTarget(
                              recoveryRuntimeValue("publicWebBaseUrl"),
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

  private boolean canUpdateRecoveryUi() {
    return !isFinishing() && (Build.VERSION.SDK_INT < 17 || !isDestroyed());
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
        enabled
            ? (filled ? Color.WHITE : Color.rgb(8, 123, 255))
            : Color.rgb(107, 112, 124));
    GradientDrawable background = new GradientDrawable();
    background.setCornerRadius(dp(24));
    if (filled) {
      background.setColor(
          enabled ? Color.rgb(8, 123, 255) : Color.rgb(233, 237, 245));
    } else {
      background.setColor(Color.TRANSPARENT);
      background.setStroke(dp(1), Color.rgb(8, 123, 255));
    }
    button.setBackground(background);
  }

  private void openRecoveryTarget(
      String target, String fallback, String failureMessage) {
    openRecoveryTarget(target, fallback, failureMessage, false);
  }

  private void openRecoveryTarget(
      String target,
      String fallback,
      String failureMessage,
      boolean recheckVersionOnReturn) {
    if (recoveryExternalOpenInFlight) {
      return;
    }
    recoveryExternalOpenInFlight = true;
    java.util.Map<String, String> recoveryRuntime = recoveryRuntimeValues();
    boolean opened =
        TrustedRecoveryUrls.open(this, target, recoveryRuntime, STARTUP_TAG);
    if (!opened && fallback != null && !fallback.isEmpty()) {
      opened = TrustedRecoveryUrls.open(this, fallback, recoveryRuntime, STARTUP_TAG);
    }
    if (!opened) {
      Toast.makeText(this, failureMessage, Toast.LENGTH_SHORT).show();
    } else if (recheckVersionOnReturn) {
      recoveryVersionRefreshPending = true;
    }
    recoveryExternalOpenInFlight = false;
  }

  private java.util.Map<String, String> recoveryRuntimeValues() {
    try {
      return runtimeConfigPackageStore.readRecoveryRuntimeValues();
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      Log.w(
          STARTUP_TAG,
          "android_recovery_runtime_config_unavailable code=" + error.code,
          error);
      return java.util.Collections.emptyMap();
    }
  }

  private String recoveryRuntimeValue(String key) {
    String value = recoveryRuntimeValues().get(key);
    return value == null ? "" : value;
  }

  private int dp(int value) {
    return Math.round(value * getResources().getDisplayMetrics().density);
  }
}
