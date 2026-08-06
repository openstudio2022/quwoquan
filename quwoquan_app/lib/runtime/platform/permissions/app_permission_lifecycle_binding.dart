import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';

/// 绑定全局 Toast 锚点与生命周期 observer，供设置返回复检使用。
class AppPermissionLifecycleBinding extends StatefulWidget {
  const AppPermissionLifecycleBinding({super.key, required this.child});

  final Widget child;

  @override
  State<AppPermissionLifecycleBinding> createState() =>
      _AppPermissionLifecycleBindingState();
}

class _AppPermissionLifecycleBindingState
    extends State<AppPermissionLifecycleBinding> {
  @override
  void initState() {
    super.initState();
    AppPermissionCoordinator.instance.ensureLifecycleAttached();
  }

  @override
  Widget build(BuildContext context) {
    AppPermissionCoordinator.instance.bindToastContext(context);
    return widget.child;
  }
}
