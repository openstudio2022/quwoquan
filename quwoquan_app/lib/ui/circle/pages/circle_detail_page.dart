import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_shell.dart';

/// 圈子主页路由入口。
///
/// 所有布局与状态管理委托给 [CircleShell] + [CircleStateNotifier]，
/// 本页仅负责接收路由参数和访问记录。
class CircleDetailPage extends ConsumerStatefulWidget {
  final String circleId;
  final VoidCallback onBack;

  const CircleDetailPage({
    super.key,
    required this.circleId,
    required this.onBack,
  });

  @override
  ConsumerState<CircleDetailPage> createState() => _CircleDetailPageState();
}

class _CircleDetailPageState extends ConsumerState<CircleDetailPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        ref.read(visitRecorderServiceProvider).recordVisit(
              VisitTarget.entity(
                kind: VisitEntityKind.circle,
                id: widget.circleId,
              ),
            );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return CircleShell(
      circleId: widget.circleId,
      onBack: widget.onBack,
    );
  }
}
