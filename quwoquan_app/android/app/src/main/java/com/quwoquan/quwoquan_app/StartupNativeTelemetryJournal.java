package com.quwoquan.quwoquan_app;

import android.content.Context;
import android.content.SharedPreferences;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;
import java.util.UUID;
import org.json.JSONObject;

/**
 * 首帧前的最小离线启动 journal。
 *
 * <p>仅写固定 allowlist 字段，绝不写账号、token、异常文本或堆栈。Flutter 成功启动后会通过
 * 启动 timing bridge 读取并转存到其可靠 journal；本类不做网络请求。
 */
final class StartupNativeTelemetryJournal {
  private static final String PREFERENCES = "FlutterSharedPreferences";
  private static final String EVENTS_KEY = "startup_telemetry_native_journal_v1";
  private static final String ATTEMPT_KEY = "startup_telemetry_native_attempt_v1";
  private static final int MAX_EVENTS = 32;

  private final SharedPreferences preferences;
  private final String attemptId;
  private int sequence;
  private long lastElapsedMs;

  StartupNativeTelemetryJournal(Context context) {
    preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    attemptId = UUID.randomUUID().toString().replace("-", "");
    preferences.edit().putString(ATTEMPT_KEY, attemptId).apply();
  }

  synchronized void record(
      String phase,
      long elapsedMs,
      String outcome,
      String recoverySurface,
      String failureCode,
      String failureSource,
      String deadlineOrigin) {
    try {
      final int nextSequence = ++sequence;
      final long normalizedElapsedMs = Math.max(0L, elapsedMs);
      final long phaseDurationMs =
          Math.max(0L, normalizedElapsedMs - lastElapsedMs);
      lastElapsedMs = Math.max(lastElapsedMs, normalizedElapsedMs);
      JSONObject event = new JSONObject();
      event.put("eventId", attemptId + "_" + nextSequence);
      event.put("attemptId", attemptId);
      event.put("sequence", nextSequence);
      event.put("phase", phase);
      event.put("phaseDurationMs", phaseDurationMs);
      event.put("elapsedMs", normalizedElapsedMs);
      event.put("outcome", outcome);
      event.put("occurredAt", utcNow());
      event.put("platform", "android");
      event.put("runtimeEnv", "unknown");
      if (!recoverySurface.isEmpty()) {
        event.put("recoverySurface", recoverySurface);
      }
      if (!failureCode.isEmpty()) {
        event.put("failureCode", failureCode);
      }
      if (!failureSource.isEmpty()) {
        event.put("failureSource", failureSource);
      }
      if (!deadlineOrigin.isEmpty()) {
        event.put("deadlineOrigin", deadlineOrigin);
      }
      Set<String> values = preferences.getStringSet(EVENTS_KEY, Collections.emptySet());
      List<String> next = new ArrayList<>(values == null ? Collections.emptySet() : values);
      next.add(event.toString());
      next.sort((left, right) -> Long.compare(eventSequence(left), eventSequence(right)));
      if (next.size() > MAX_EVENTS) {
        next = next.subList(next.size() - MAX_EVENTS, next.size());
      }
      preferences.edit().putStringSet(EVENTS_KEY, new HashSet<>(next)).apply();
    } catch (Exception ignored) {
      // 记录失败不能让原生 watchdog 或 Activity 生命周期崩溃。
    }
  }

  synchronized String attemptId() {
    return attemptId;
  }

  synchronized List<String> events() {
    Set<String> values = preferences.getStringSet(EVENTS_KEY, Collections.emptySet());
    return new ArrayList<>(values == null ? Collections.emptySet() : values);
  }

  synchronized void clearEvents() {
    preferences.edit().remove(EVENTS_KEY).apply();
  }

  private static String utcNow() {
    SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
    formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
    return formatter.format(new Date());
  }

  private static long eventSequence(String encoded) {
    try {
      return new JSONObject(encoded).optLong("sequence", Long.MAX_VALUE);
    } catch (Exception ignored) {
      return Long.MAX_VALUE;
    }
  }
}
