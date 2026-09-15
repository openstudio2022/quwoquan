package com.quwoquan.quwoquan_app;

import android.app.Activity;
import android.content.res.Configuration;
import android.os.Looper;
import android.view.Display;
import android.view.View;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/** 只读当前宿主界面事实，不读取传感器或请求策略。 */
final class NativeOrientationReader {
  private View boundView;
  private int displayId = -1;
  private String binding;

  void invalidate() {
    boundView = null;
    displayId = -1;
    binding = null;
  }

  Map<String, Object> read(Activity activity, boolean foreground) {
    Map<String, Object> result = new HashMap<>();
    result.put(NativeOrientationContract.field_platform, NativeOrientationContract.value_android);
    result.put(NativeOrientationContract.field_status, NativeOrientationContract.value_unavailable);
    if (Looper.myLooper() != Looper.getMainLooper() || !foreground || activity.isFinishing() || activity.isDestroyed()) {
      invalidate();
      return result;
    }
    View view = activity.getWindow().getDecorView();
    Display display = view.getDisplay();
    if (!view.isAttachedToWindow() || !view.hasWindowFocus() || display == null || !display.isValid()) {
      invalidate();
      return result;
    }
    int orientation = activity.getResources().getConfiguration().orientation;
    if (orientation != Configuration.ORIENTATION_PORTRAIT && orientation != Configuration.ORIENTATION_LANDSCAPE) {
      invalidate();
      return result;
    }
    if (boundView != view || displayId != display.getDisplayId()) {
      boundView = view;
      displayId = display.getDisplayId();
      binding = UUID.randomUUID().toString();
    }
    int rotation = display.getRotation();
    if (rotation < 0 || rotation > 3) { invalidate(); return result; }
    result.put(NativeOrientationContract.field_status, NativeOrientationContract.value_available);
    result.put(NativeOrientationContract.field_binding, binding);
    result.put(NativeOrientationContract.field_axis, orientation == Configuration.ORIENTATION_PORTRAIT
        ? NativeOrientationContract.value_portrait : NativeOrientationContract.value_landscape);
    result.put(NativeOrientationContract.field_rotation, rotation * 90);
    return result;
  }
}
