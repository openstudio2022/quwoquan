package com.quwoquan.quwoquan_app;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

enum StartupSafeTerminalSurface {
  ROUTER_SHELL("router_shell", true, true),
  SAFE_RECOVERY("safe_recovery", false, true),
  FLUTTER_RECOVERY("flutter_recovery", false, true),
  MISSING("missing", false, false),
  UNKNOWN("unknown", false, false);

  private static final Pattern SURFACE_PATTERN =
      Pattern.compile("\\\"surface\\\"\\s*:\\s*\\\"([a-z_]+)\\\"");

  private final String markerValue;
  private final boolean canonical;
  private final boolean recognizedSafeSurface;

  StartupSafeTerminalSurface(
      String markerValue, boolean canonical, boolean recognizedSafeSurface) {
    this.markerValue = markerValue;
    this.canonical = canonical;
    this.recognizedSafeSurface = recognizedSafeSurface;
  }

  static StartupSafeTerminalSurface fromEvent(String event) {
    if (event == null || event.isEmpty()) {
      return MISSING;
    }
    Matcher matcher = SURFACE_PATTERN.matcher(event);
    if (!matcher.find()) {
      return MISSING;
    }
    switch (matcher.group(1)) {
      case "router_shell":
        return ROUTER_SHELL;
      case "safe_recovery":
        return SAFE_RECOVERY;
      case "flutter_recovery":
        return FLUTTER_RECOVERY;
      default:
        return UNKNOWN;
    }
  }

  String markerValue() {
    return markerValue;
  }

  boolean isCanonical() {
    return canonical;
  }

  boolean isRecognizedSafeSurface() {
    return recognizedSafeSurface;
  }
}
