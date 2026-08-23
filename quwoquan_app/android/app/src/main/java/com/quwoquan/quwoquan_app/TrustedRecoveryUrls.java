package com.quwoquan.quwoquan_app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.util.Log;
import java.util.Map;

/** 原生恢复与 Flutter bridge 共用的受信 HTTPS URL 解析器。 */
final class TrustedRecoveryUrls {
  private TrustedRecoveryUrls() {}

  static boolean open(
      Activity activity, String rawUrl, Map<String, String> configuredBases, String logTag) {
    Uri uri = parse(rawUrl, configuredBases);
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

  static boolean isTrusted(String rawUrl, Map<String, String> configuredBases) {
    return parse(rawUrl, configuredBases) != null;
  }

  private static Uri parse(String rawUrl, Map<String, String> configuredBases) {
    try {
      Uri uri = Uri.parse(rawUrl == null ? "" : rawUrl.trim());
      String host = uri.getHost();
      if (!"https".equalsIgnoreCase(uri.getScheme())
          || host == null
          || host.isEmpty()
          || uri.getUserInfo() != null
          || uri.getFragment() != null
          || configuredBases == null
          || (!matchesConfiguredBase(uri, configuredBases.get("gatewayBaseUrl"))
              && !matchesConfiguredBase(uri, configuredBases.get("publicWebBaseUrl"))
              && !matchesConfiguredBase(uri, configuredBases.get("appDownloadBaseUrl")))) {
        return null;
      }
      return uri;
    } catch (RuntimeException ignored) {
      return null;
    }
  }

  private static boolean matchesConfiguredBase(Uri candidate, String rawBase) {
    Uri base = Uri.parse(rawBase == null ? "" : rawBase.trim());
    if (!"https".equalsIgnoreCase(base.getScheme())
        || base.getHost() == null
        || !base.getHost().equalsIgnoreCase(candidate.getHost())
        || effectivePort(base) != effectivePort(candidate)) {
      return false;
    }
    String basePath = base.getPath() == null ? "" : base.getPath().replaceAll("/+$", "");
    String candidatePath = candidate.getPath() == null ? "" : candidate.getPath();
    return basePath.isEmpty()
        || candidatePath.equals(basePath)
        || candidatePath.startsWith(basePath + "/");
  }

  private static int effectivePort(Uri uri) {
    return uri.getPort() == -1 ? 443 : uri.getPort();
  }
}
