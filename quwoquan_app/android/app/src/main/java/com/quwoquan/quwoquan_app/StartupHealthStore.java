package com.quwoquan.quwoquan_app;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;
import org.json.JSONObject;

/** 启动致命证据与安全 Shell 状态的唯一原生真相源。 */
final class StartupHealthStore {
  private static final String PREFERENCES = "quwoquan.runtime.diagnostics";
  private static final String CRASH_KIND_KEY = "previous_native_crash_kind";
  private static final String BUILD_IDENTITY_KEY = "startup_health_build";
  private static final String STARTED_AT_KEY = "startup_health_started_at";
  private static final String SAFE_SHELL_KEY = "startup_health_safe_shell";
  private static final String FATAL_BUILD_IDENTITY_KEY = "startup_health_fatal_build";
  private static final String FATAL_AT_KEY = "startup_health_fatal_at";
  private static final String FATAL_QUEUED_IDENTITY_KEY =
      "startup_health_fatal_queued_identity";
  private static final int MAX_RECOVERY_RECORDS = 20;
  private static final int MAX_RECOVERY_RECORD_BYTES = 64 << 10;
  private static final long RECOVERY_RETENTION_MS = TimeUnit.DAYS.toMillis(7);
  private static volatile boolean crashMarkerInstalled;

  private StartupHealthStore() {}

  static void installNativeCrashMarker(Context context) {
    Context applicationContext = context.getApplicationContext();
    synchronized (StartupHealthStore.class) {
      if (crashMarkerInstalled) {
        return;
      }
      crashMarkerInstalled = true;
      Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
      Thread.setDefaultUncaughtExceptionHandler(
          (thread, error) -> {
            persistNativeCrashMarker(applicationContext, error);
            if (previous != null) {
              previous.uncaughtException(thread, error);
              return;
            }
            // Delegating to ThreadGroup after installing this handler can route
            // back to the default handler and recurse indefinitely.
            android.os.Process.killProcess(android.os.Process.myPid());
            System.exit(10);
          });
    }
  }

  static void promoteConfirmedPlatformStartupCrash(Context context) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
      return;
    }
    SharedPreferences preferences = preferences(context);
    String identity = currentArtifactIdentity(context);
    String previousIdentity = preferences.getString(BUILD_IDENTITY_KEY, "");
    long previousStartedAt = preferences.getLong(STARTED_AT_KEY, 0L);
    boolean previousSafeShell = preferences.getBoolean(SAFE_SHELL_KEY, true);
    if (!identity.equals(previousIdentity)
        || previousSafeShell
        || previousStartedAt <= 0L) {
      return;
    }

    ActivityManager manager =
        (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
    if (manager == null) {
      return;
    }
    ApplicationExitInfo latestExit = null;
    try {
      for (ApplicationExitInfo exit :
          manager.getHistoricalProcessExitReasons(context.getPackageName(), 0, 5)) {
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
    if (latestExit.getTimestamp() < previousStartedAt) {
      // Historical exits may include an older crash from the same artifact. Only
      // the process attempt marked immediately before this gate is admissible.
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
        .putString(FATAL_BUILD_IDENTITY_KEY, identity)
        .putLong(FATAL_AT_KEY, latestExit.getTimestamp())
        .putString(CRASH_KIND_KEY, kind)
        .commit();
  }

  static boolean shouldRecoverConfirmedStartupFatal(Context context) {
    SharedPreferences preferences = preferences(context);
    String fatalIdentity = preferences.getString(FATAL_BUILD_IDENTITY_KEY, "");
    if (fatalIdentity == null || fatalIdentity.isEmpty()) {
      return false;
    }
    if (!currentArtifactIdentity(context).equals(fatalIdentity)) {
      clearFatalMarker(preferences, "artifact_mismatch");
      return false;
    }
    if (!currentArtifactIdentity(context).equals(preferences.getString(BUILD_IDENTITY_KEY, ""))) {
      clearFatalMarker(preferences, "artifact_mismatch");
      return false;
    }
    if (preferences.getBoolean(SAFE_SHELL_KEY, false)) {
      clearFatalMarker(preferences, "safe_shell_conflict");
      return false;
    }
    return true;
  }

  static void markCurrentArtifactStarting(Context context) {
    preferences(context)
        .edit()
        .putString(BUILD_IDENTITY_KEY, currentArtifactIdentity(context))
        .putLong(STARTED_AT_KEY, System.currentTimeMillis())
        .putBoolean(SAFE_SHELL_KEY, false)
        .commit();
  }

  static boolean markCurrentArtifactFatal(Context context) {
    SharedPreferences preferences = preferences(context);
    String identity = currentArtifactIdentity(context);
    if (!identity.equals(preferences.getString(BUILD_IDENTITY_KEY, ""))
        || preferences.getBoolean(SAFE_SHELL_KEY, false)) {
      return false;
    }
    return preferences
        .edit()
        .putString(FATAL_BUILD_IDENTITY_KEY, identity)
        .putLong(FATAL_AT_KEY, System.currentTimeMillis())
        .commit();
  }

  static void markCurrentArtifactSafeShell(Context context) {
    preferences(context)
        .edit()
        .putString(BUILD_IDENTITY_KEY, currentArtifactIdentity(context))
        .putBoolean(SAFE_SHELL_KEY, true)
        .remove(FATAL_BUILD_IDENTITY_KEY)
        .remove(FATAL_AT_KEY)
        .remove(FATAL_QUEUED_IDENTITY_KEY)
        .apply();
  }

  static boolean enqueueConfirmedStartupFatal(Context context) {
    SharedPreferences preferences = preferences(context);
    String identity = currentArtifactIdentity(context);
    if (!identity.equals(preferences.getString(FATAL_BUILD_IDENTITY_KEY, ""))) {
      return false;
    }
    if (identity.equals(preferences.getString(FATAL_QUEUED_IDENTITY_KEY, ""))) {
      return true;
    }
    long occurredAtMs = preferences.getLong(FATAL_AT_KEY, 0L);
    if (occurredAtMs <= 0L) {
      return false;
    }
    String kind = preferences.getString(CRASH_KIND_KEY, "NativeStartupCrash");
    try {
      String occurredAt = utcTimestamp(occurredAtMs);
      JSONObject failure = new JSONObject();
      failure.put("occurredAt", occurredAt);
      failure.put("appVersion", BuildConfig.VERSION_NAME);
      failure.put("buildNumber", String.valueOf(BuildConfig.VERSION_CODE));
      failure.put("platform", "android");
      failure.put("osVersion", Build.VERSION.RELEASE);
      failure.put("deviceModel", Build.MODEL);
      failure.put("errorSource", "native");
      failure.put("errorType", normalizeType(kind));
      failure.put("errorMessage", "Native startup terminated before safe shell");
      failure.put("stackTrace", "Native stack unavailable after process termination");
      if (failure.toString().getBytes(StandardCharsets.UTF_8).length
          > MAX_RECOVERY_RECORD_BYTES) {
        return false;
      }

      RecoveryFailureEncryptedStore store =
          new RecoveryFailureEncryptedStore(context.getApplicationContext());
      JSONArray existing = readRecoveryQueue(store.read());
      List<JSONObject> retained = new ArrayList<>();
      long now = System.currentTimeMillis();
      for (int index = 0; index < existing.length(); index += 1) {
        JSONObject entry = existing.optJSONObject(index);
        if (entry == null) {
          continue;
        }
        long savedAtMs = parseTimestamp(entry.optString("savedAt", ""));
        if (savedAtMs > 0L && now - savedAtMs <= RECOVERY_RETENTION_MS) {
          retained.add(entry);
        }
      }
      JSONObject queued = new JSONObject();
      queued.put("failure", failure);
      queued.put("savedAt", occurredAt);
      queued.put("attempts", 0);
      retained.add(queued);
      while (retained.size() > MAX_RECOVERY_RECORDS) {
        retained.remove(0);
      }
      JSONArray output = new JSONArray();
      for (JSONObject entry : retained) {
        output.put(entry);
      }
      if (!store.write(output.toString())) {
        return false;
      }
      preferences.edit().putString(FATAL_QUEUED_IDENTITY_KEY, identity).apply();
      return true;
    } catch (Exception ignored) {
      return false;
    }
  }

  static Map<String, Object> consumePreviousRuntimeCrash(Context context) {
    SharedPreferences preferences = preferences(context);
    String kind = preferences.getString(CRASH_KIND_KEY, "");
    if (kind == null || kind.trim().isEmpty()) {
      return null;
    }
    preferences.edit().remove(CRASH_KIND_KEY).apply();
    Map<String, Object> marker = new HashMap<>();
    marker.put("kind", kind);
    return marker;
  }

  static void acknowledgeCrashMarker(Context context) {
    preferences(context).edit().remove(CRASH_KIND_KEY).apply();
  }

  /** Clears startup health markers for Android instrumentation only. */
  static void clearAllMarkersForInstrumentedTest(Context context) {
    preferences(context).edit().clear().commit();
  }

  /** Seeds a same-artifact confirmed fatal for Android instrumentation only. */
  static void seedConfirmedStartupFatalForInstrumentedTest(Context context) {
    preferences(context)
        .edit()
        .putString(FATAL_BUILD_IDENTITY_KEY, currentArtifactIdentity(context))
        .putLong(FATAL_AT_KEY, System.currentTimeMillis())
        .putBoolean(SAFE_SHELL_KEY, false)
        .putString(BUILD_IDENTITY_KEY, currentArtifactIdentity(context))
        .putLong(STARTED_AT_KEY, System.currentTimeMillis() - 1_000L)
        .commit();
  }

  /** Seeds the impossible safe-shell/fatal combination for self-healing coverage. */
  static void seedSafeShellConflictForInstrumentedTest(Context context) {
    preferences(context)
        .edit()
        .putString(FATAL_BUILD_IDENTITY_KEY, currentArtifactIdentity(context))
        .putLong(FATAL_AT_KEY, System.currentTimeMillis())
        .putString(FATAL_QUEUED_IDENTITY_KEY, currentArtifactIdentity(context))
        .putBoolean(SAFE_SHELL_KEY, true)
        .putString(BUILD_IDENTITY_KEY, currentArtifactIdentity(context))
        .commit();
  }

  /** Seeds a marker from a different immutable artifact for stale cleanup coverage. */
  static void seedArtifactMismatchForInstrumentedTest(Context context) {
    preferences(context)
        .edit()
        .putString(FATAL_BUILD_IDENTITY_KEY, "stale-artifact")
        .putLong(FATAL_AT_KEY, System.currentTimeMillis())
        .putString(FATAL_QUEUED_IDENTITY_KEY, "stale-artifact")
        .putBoolean(SAFE_SHELL_KEY, false)
        .putString(BUILD_IDENTITY_KEY, "stale-artifact")
        .commit();
  }

  private static void persistNativeCrashMarker(Context context, Throwable error) {
    try {
      String kind = error == null ? "UnknownNativeError" : error.getClass().getSimpleName();
      if (kind == null || kind.trim().isEmpty()) {
        kind = "UnknownNativeError";
      }
      kind = kind.replaceAll("[^A-Za-z0-9_.-]", "_");
      if (kind.length() > 80) {
        kind = kind.substring(0, 80);
      }
      SharedPreferences preferences = preferences(context);
      preferences.edit().putString(CRASH_KIND_KEY, kind).commit();
      if (!preferences.getBoolean(SAFE_SHELL_KEY, false)) {
        markCurrentArtifactFatal(context);
      }
    } catch (RuntimeException ignored) {
      // Observability must never replace the platform crash path.
    }
  }

  private static void clearFatalMarker(SharedPreferences preferences, String reason) {
    preferences
        .edit()
        .remove(FATAL_BUILD_IDENTITY_KEY)
        .remove(FATAL_AT_KEY)
        .remove(FATAL_QUEUED_IDENTITY_KEY)
        .commit();
    Log.i("QWQStartup", "startup_fatal_marker_stale_cleared reason=" + reason);
  }

  private static SharedPreferences preferences(Context context) {
    return context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
  }

  private static String currentArtifactIdentity(Context context) {
    return BuildConfig.VERSION_CODE
        + "|"
        + AndroidRuntimeConfig.createStore(context).currentIdentity();
  }

  private static JSONArray readRecoveryQueue(String raw) {
    if (raw == null || raw.trim().isEmpty()) {
      return new JSONArray();
    }
    try {
      return new JSONArray(raw);
    } catch (Exception ignored) {
      return new JSONArray();
    }
  }

  private static String normalizeType(String raw) {
    String value = raw == null ? "" : raw.replaceAll("[^A-Za-z0-9_.-]", "_");
    if (value.isEmpty()) {
      return "NativeStartupCrash";
    }
    return value.length() <= 80 ? value : value.substring(0, 80);
  }

  private static String utcTimestamp(long milliseconds) {
    SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
    formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
    return formatter.format(new Date(milliseconds));
  }

  private static long parseTimestamp(String raw) {
    try {
      SimpleDateFormat formatter =
          new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
      formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
      Date parsed = formatter.parse(raw);
      return parsed == null ? 0L : parsed.getTime();
    } catch (Exception ignored) {
      return 0L;
    }
  }
}
