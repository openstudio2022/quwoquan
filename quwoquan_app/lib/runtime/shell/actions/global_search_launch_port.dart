import 'package:flutter/widgets.dart';

/// 全局壳层发起搜索落地的端口。
///
/// 壳层只声明「按入口 surface 与 scope wire 打开搜索」这一能力；
/// `SearchLaunchContext` / `SearchScope` 属于 search 域，由组合根
/// `lib/runtime/di/**` 注入实现。本文件不得 import 任何 domain 类型。
abstract interface class GlobalSearchLaunchPort {
  Future<void> open(
    BuildContext context, {
    required String entrySurfaceId,
    String initialScopeWire = 'all',
    String prefilledQuery = '',
  });
}
