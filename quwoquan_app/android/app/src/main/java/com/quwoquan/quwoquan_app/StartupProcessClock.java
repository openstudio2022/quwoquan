package com.quwoquan.quwoquan_app;

import android.os.Process;
import android.os.SystemClock;

/**
 * Process-monotonic startup clock shared by the native gate, Flutter host and Dart timing bridge.
 *
 * <p>The clock is initialized by {@link QuwoquanApplication} before any Activity is created. Keeping
 * it outside MainActivity prevents the Gate → Main handoff from incorrectly redefining process start.
 */
final class StartupProcessClock {
  private static long processStartElapsedMs;

  private StartupProcessClock() {}

  static synchronized void initialize() {
    if (processStartElapsedMs == 0L) {
      long now = SystemClock.elapsedRealtime();
      long platformProcessStart = Process.getStartElapsedRealtime();
      processStartElapsedMs =
          platformProcessStart > 0L && platformProcessStart <= now ? platformProcessStart : now;
    }
  }

  static long processStartElapsedMs() {
    initialize();
    return processStartElapsedMs;
  }

  static long elapsedSinceProcessStartMs() {
    return Math.max(0L, SystemClock.elapsedRealtime() - processStartElapsedMs());
  }
}
