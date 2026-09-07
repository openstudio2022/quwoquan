import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';
import 'package:quwoquan_app/runtime/shell/actions/global_surface_actions.dart';

/// 对象页（实体 / 圈子主页）底部全局导航栏。
///
/// 高保口径：详情页底部保留与首页一致的全局底栏（首页/视频书/+/联系/我），
/// 复用 [BottomNavigationWidget]，与主壳同款 token / 图标 / 尺寸。
///
/// 行为：加号 → 全局创建动作面板（[GlobalQuickActionSheet]，登录拦截下沉到具体动作）；
/// 其余 tab → `context.go` 回对应根 tab（根壳重建后由 [MainTabDestination] 的登录门与
/// 占位兜底接管）。详情页不属于任何 tab，故不高亮任一项（传超出范围的 index）。
class ObjectDetailGlobalBottomNav extends ConsumerWidget {
  const ObjectDetailGlobalBottomNav({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return BottomNavigationWidget(
      // 详情页不归属任何根 tab：传超出 0..n-1 范围的 index 关闭高亮。
      currentIndex: MainTabDestinationX.bottomNavOrdered.length,
      onTap: (index) {
        final tab = mainTabFromBottomNavIndex(index);
        if (tab == MainTabDestination.create) {
          unawaited(GlobalQuickActionSheet.show(context, ref));
          return;
        }
        context.go(tab.routePath);
      },
    );
  }
}
