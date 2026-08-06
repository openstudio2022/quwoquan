import 'dart:async';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/application/public/circle_behavior_fact_appender.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_app/runtime/di/presentation/circle_shell.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_engagement_tracker.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_appearance.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AppendCircleBehaviorFactCommand, BehaviorEventType;

/// 圈子主页路由入口。
///
/// 所有布局与状态管理委托给 [CircleShell] + [CircleStateNotifier]，
/// 本页仅负责接收路由参数、访问记录与圈子对象级行为信号
/// （impression/dwell 进入推荐 HotPath）。
class CircleDetailPage extends StatefulWidget {
  final String circleId;
  final VoidCallback onBack;
  final VisitRecorderService visitRecorderService;
  final ContentEngagementTracker contentEngagementTracker;
  final bool hasAuthenticatedOwner;
  final CircleBehaviorFactAppender? behaviorFactAppender;
  final CircleMembershipApprovalPageBuilder membershipApprovalPageBuilder;
  final CircleGroupMembershipAccess? groupMembershipAccess;
  final ReferralSource referralSource;
  final UiErrorAppearanceMode sourceAppearanceMode;

  const CircleDetailPage({
    super.key,
    required this.circleId,
    required this.onBack,
    required this.visitRecorderService,
    required this.contentEngagementTracker,
    required this.hasAuthenticatedOwner,
    required this.behaviorFactAppender,
    required this.membershipApprovalPageBuilder,
    this.groupMembershipAccess,
    this.referralSource = ReferralSource.organicFeed,
    this.sourceAppearanceMode = UiErrorAppearanceMode.inherit,
  }) : assert(!hasAuthenticatedOwner || behaviorFactAppender != null);

  @override
  State<CircleDetailPage> createState() => _CircleDetailPageState();
}

class _CircleDetailPageState extends State<CircleDetailPage> {
  /// 首帧后冻结一次：dwell 与 impression 使用同一认证 actor/writer。
  CircleBehaviorFactAppender? _behaviorFactWriter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        widget.visitRecorderService.recordVisit(
          VisitTarget.entity(kind: VisitEntityKind.circle, id: widget.circleId),
        );
        widget.contentEngagementTracker.trackEntityPageView(
          widget.circleId,
          from: widget.referralSource,
        );
        // 行为事实要求可信 persona：游客态不解析 writer（不产生 401 噪音）。
        if (widget.hasAuthenticatedOwner) {
          _behaviorFactWriter = widget.behaviorFactAppender;
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
      membershipApprovalPageBuilder: widget.membershipApprovalPageBuilder,
      groupMembershipAccess: widget.groupMembershipAccess,
      onBack: widget.onBack,
      sourceAppearanceMode: widget.sourceAppearanceMode,
    );
  }
}
