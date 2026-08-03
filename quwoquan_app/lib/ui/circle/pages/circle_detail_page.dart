import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_shell.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AppendCircleBehaviorFactCommand,
        BehaviorEventType,
        CircleBehaviorFactWriter;

/// 圈子主页路由入口。
///
/// 所有布局与状态管理委托给 [CircleShell] + [CircleStateNotifier]，
/// 本页仅负责接收路由参数、访问记录与圈子对象级行为信号
/// （impression/dwell 进入推荐 HotPath）。
class CircleDetailPage extends ConsumerStatefulWidget {
  final String circleId;
  final VoidCallback onBack;
  final ReferralSource referralSource;
  final UiErrorAppearanceMode sourceAppearanceMode;

  const CircleDetailPage({
    super.key,
    required this.circleId,
    required this.onBack,
    this.referralSource = ReferralSource.organicFeed,
    this.sourceAppearanceMode = UiErrorAppearanceMode.inherit,
  });

  @override
  ConsumerState<CircleDetailPage> createState() => _CircleDetailPageState();
}

class _CircleDetailPageState extends ConsumerState<CircleDetailPage> {
  /// 首帧后解析一次：dispose 阶段禁止再使用 ref，dwell 信号消费该缓存。
  CircleBehaviorFactWriter? _behaviorFactWriter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        ref
            .read(visitRecorderServiceProvider)
            .recordVisit(
              VisitTarget.entity(
                kind: VisitEntityKind.circle,
                id: widget.circleId,
              ),
            );
        ref
            .read(contentEngagementTrackerProvider)
            .trackEntityPageView(widget.circleId, from: widget.referralSource);
        // 行为事实要求可信 persona：游客态不解析 writer（不产生 401 噪音）。
        if (ref.read(resolvedOwnerUserIdProvider).trim().isNotEmpty) {
          _behaviorFactWriter = ref.read(
            circleDetailBehaviorFactWriterProvider,
          );
        }
        _appendCircleBehaviorFact(BehaviorEventType.impression);
      }
    });
  }

  @override
  void dispose() {
    _appendCircleBehaviorFact(BehaviorEventType.dwell);
    super.dispose();
  }

  /// fire-and-forget：行为信号失败不影响页面交互，经全局异常遥测观测。
  void _appendCircleBehaviorFact(BehaviorEventType eventType) {
    final writer = _behaviorFactWriter;
    if (writer == null) {
      return;
    }
    unawaited(
      writer
          .append(
            AppendCircleBehaviorFactCommand(
              circleId: widget.circleId,
              eventType: eventType,
            ),
          )
          .catchError((Object error, StackTrace stackTrace) {
            unawaited(
              AppExceptionTelemetryService.instance.recordGlobalException(
                source: 'circle.behavior.${eventType.wireName}',
                exceptionText: error.toString(),
                stackText: stackTrace.toString(),
              ),
            );
          }),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CircleShell(
      circleId: widget.circleId,
      onBack: widget.onBack,
      sourceAppearanceMode: widget.sourceAppearanceMode,
    );
  }
}
