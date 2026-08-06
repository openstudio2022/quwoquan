import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

/// 兼容旧调用点：统一打开全屏本地草稿页。
Future<void> presentCreateDraftPickerAndGo(
  BuildContext _,
  GoRouter router,
) async {
  router.push(AppRoutePaths.localDrafts);
}
