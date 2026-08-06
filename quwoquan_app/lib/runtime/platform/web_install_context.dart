import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/core/platform/web_install_context_stub.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/core/platform/web_install_context_web.dart';

enum WebInstallRecommendation { android, ios, desktop, unknown }

@immutable
class WebInstallContext {
  const WebInstallContext({
    required this.recommendation,
    required this.isStandalone,
    required this.dismissedForSession,
  });

  const WebInstallContext.unknown()
    : this(
        recommendation: WebInstallRecommendation.unknown,
        isStandalone: false,
        dismissedForSession: false,
      );

  final WebInstallRecommendation recommendation;
  final bool isStandalone;
  final bool dismissedForSession;
}

WebInstallContext readWebInstallContext() {
  try {
    final raw = readWebInstallContextJson();
    final decoded = jsonDecode(raw);
    if (decoded is! Map) {
      return const WebInstallContext.unknown();
    }
    final recommendation = switch (decoded['platform']?.toString()) {
      'android' => WebInstallRecommendation.android,
      'ios' => WebInstallRecommendation.ios,
      'desktop' => WebInstallRecommendation.desktop,
      _ => WebInstallRecommendation.unknown,
    };
    return WebInstallContext(
      recommendation: recommendation,
      isStandalone: decoded['standalone'] == true,
      dismissedForSession: decoded['dismissed'] == true,
    );
  } catch (_) {
    return const WebInstallContext.unknown();
  }
}

void dismissWebInstallForSession() {
  try {
    persistWebInstallDismissal();
  } catch (_) {
    // 浏览器拒绝 sessionStorage 时仍允许当前 Widget 会话隐藏。
  }
}
