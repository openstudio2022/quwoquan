package com.quwoquan.quwoquan_app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import android.view.ViewGroup;

@SuppressWarnings("deprecation")
public class StartupActivity extends Activity {
  private static final String STARTUP_TAG = "QWQStartup";
  private long activityCreateMs = 0L;
  private boolean handedOff = false;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    activityCreateMs = SystemClock.uptimeMillis();
    super.onCreate(savedInstanceState);
    Log.i(STARTUP_TAG, "android_startup_activity_on_create");

    getWindow().setBackgroundDrawable(
        getResources().getDrawable(R.drawable.launch_background, getTheme()));
    NativeWelcomeView root =
        new NativeWelcomeView(this, activityCreateMs, "android_startup_welcome_first_draw");
    setContentView(
        root,
        new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

    root.post(this::openMainActivity);
  }

  @Override
  protected void onResume() {
    super.onResume();
    if (handedOff) {
      finish();
      overridePendingTransition(0, 0);
    }
  }

  private void openMainActivity() {
    if (isFinishing() || handedOff) {
      return;
    }
    handedOff = true;
    Intent intent = new Intent(getIntent());
    intent.setClass(this, MainActivity.class);
    intent.addFlags(Intent.FLAG_ACTIVITY_NO_ANIMATION);
    intent.putExtra("nativeStartupStartedElapsedRealtime", activityCreateMs);
    startActivity(intent);
    overridePendingTransition(0, 0);
    Log.i(
        STARTUP_TAG,
        "android_startup_activity_handoff elapsedMs="
            + (SystemClock.uptimeMillis() - activityCreateMs));
  }
}
