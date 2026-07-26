package com.quwoquan.quwoquan_app;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.ArrayList;
import java.util.List;

/**
 * 清理旧版启动 journal 的兼容壳。
 *
 * <p>恢复规格不再生成 attemptId、checkpoint 或第二套启动异常上报。保留空接口只是为了让
 * 既有 timing bridge 在滚动升级期返回空结果，后续可随旧 bridge 一并删除。
 */
final class StartupNativeTelemetryJournal {
  private static final String PREFERENCES = "FlutterSharedPreferences";
  private static final String EVENTS_KEY = "startup_telemetry_native_journal";
  private static final String ATTEMPT_KEY = "startup_telemetry_native_attempt";

  private final SharedPreferences preferences;

  StartupNativeTelemetryJournal(Context context) {
    preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    preferences.edit().remove(ATTEMPT_KEY).remove(EVENTS_KEY).apply();
  }

  synchronized void record(
      String phase,
      long elapsedMs,
      String outcome,
      String recoverySurface,
      String failureCode,
      String failureSource,
      String deadlineOrigin) {
    // Intentionally empty.
  }

  synchronized String attemptId() {
    return "";
  }

  synchronized List<String> events() {
    return new ArrayList<>();
  }

  synchronized void clearEvents() {
    preferences.edit().remove(EVENTS_KEY).remove(ATTEMPT_KEY).apply();
  }
}
