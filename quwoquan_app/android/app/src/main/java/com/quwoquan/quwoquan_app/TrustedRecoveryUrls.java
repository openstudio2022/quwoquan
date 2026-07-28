package com.quwoquan.quwoquan_app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.util.Log;
import java.util.Locale;

/** 原生恢复与 Flutter bridge 共用的受信 HTTPS URL 解析器。 */
final class TrustedRecoveryUrls {
  private TrustedRecoveryUrls() {}

  static boolean open(Activity activity, String rawUrl, String logTag) {
    Uri uri = parse(rawUrl);
    if (uri == null) {
      return false;
    }
    try {
      Intent intent = new Intent(Intent.ACTION_VIEW, uri);
      intent.addCategory(Intent.CATEGORY_BROWSABLE);
      activity.startActivity(intent);
      return true;
    } catch (RuntimeException error) {
      Log.w(logTag, "android_recovery_external_open_failed", error);
      return false;
    }
  }

  static boolean isTrusted(String rawUrl) {
    return parse(rawUrl) != null;
  }

  private static Uri parse(String rawUrl) {
    try {
      Uri uri = Uri.parse(rawUrl == null ? "" : rawUrl.trim());
      String host = uri.getHost();
      if (!"https".equalsIgnoreCase(uri.getScheme())
          || host == null
          || host.isEmpty()
          || uri.getUserInfo() != null
          || !isTrustedHost(host)) {
        return null;
      }
      return uri;
    } catch (RuntimeException ignored) {
      return null;
    }
  }

  private static boolean isTrustedHost(String rawHost) {
    String host = rawHost.toLowerCase(Locale.ROOT);
    return host.equals("quwoquan.com") || host.endsWith(".quwoquan.com");
  }
}
