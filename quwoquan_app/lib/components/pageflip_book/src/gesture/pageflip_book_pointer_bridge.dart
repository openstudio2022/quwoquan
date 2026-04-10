import 'package:flutter/foundation.dart';

@immutable
class PageflipBookPointerBridgeConfig {
  const PageflipBookPointerBridgeConfig({
    this.swipeTimeout = const Duration(milliseconds: 250),
    this.swipeDistance = 30,
    this.moveStartDistance = 10,
  });

  final Duration swipeTimeout;
  final double swipeDistance;
  final double moveStartDistance;
}
