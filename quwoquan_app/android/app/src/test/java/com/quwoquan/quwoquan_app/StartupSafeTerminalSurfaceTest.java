package com.quwoquan.quwoquan_app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class StartupSafeTerminalSurfaceTest {
  @Test
  public void parserPreservesEveryDeclaredDartSurface() {
    assertEquals(
        StartupSafeTerminalSurface.ROUTER_SHELL,
        StartupSafeTerminalSurface.fromEvent(event("router_shell")));
    assertEquals(
        StartupSafeTerminalSurface.SAFE_RECOVERY,
        StartupSafeTerminalSurface.fromEvent(event("safe_recovery")));
    assertEquals(
        StartupSafeTerminalSurface.FLUTTER_RECOVERY,
        StartupSafeTerminalSurface.fromEvent(event("flutter_recovery")));
  }

  @Test
  public void onlyRouterShellIsCanonical() {
    assertTrue(StartupSafeTerminalSurface.ROUTER_SHELL.isCanonical());
    assertFalse(StartupSafeTerminalSurface.SAFE_RECOVERY.isCanonical());
    assertFalse(StartupSafeTerminalSurface.FLUTTER_RECOVERY.isCanonical());
    assertFalse(StartupSafeTerminalSurface.MISSING.isCanonical());
    assertFalse(StartupSafeTerminalSurface.UNKNOWN.isCanonical());
  }

  @Test
  public void missingAndUnknownSurfacesRemainTyped() {
    assertEquals(
        StartupSafeTerminalSurface.MISSING,
        StartupSafeTerminalSurface.fromEvent(
            "{\"eventName\":\"startup_safe_terminal\"}"));
    assertEquals(
        StartupSafeTerminalSurface.UNKNOWN,
        StartupSafeTerminalSurface.fromEvent(event("future_surface")));
  }

  private static String event(String surface) {
    return "{\"eventName\":\"startup_safe_terminal\",\"surface\":\""
        + surface
        + "\"}";
  }
}
