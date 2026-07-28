package com.quwoquan.quwoquan_app;

import android.app.Application;

/** Establishes process-wide startup diagnostics before the launcher Activity is created. */
public final class QuwoquanApplication extends Application {
  @Override
  public void onCreate() {
    StartupProcessClock.initialize();
    StartupHealthStore.installNativeCrashMarker(this);
    super.onCreate();
  }
}
