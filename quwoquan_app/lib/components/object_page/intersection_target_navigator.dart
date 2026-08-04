import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/models/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/core/models/start_group_chat_route_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/assistant/assistant/page_context/domain/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';

/// 交集导航归因（埋点上下文），由展示面在构造导航器时透传。
///
/// 不承载任何人类可读结论句，只携带可观测/归因标识，供 [IntersectionTargetNavigator.open]
/// 在跳转时上报（contentBehaviorTracker.trackClick）。
class IntersectionNavAttribution {
  const IntersectionNavAttribution({
    this.intersectionId = '',
    this.dimension = '',
    this.intersectionClass = '',
    this.sourceRef = '',
    this.tagRefs = const <String>[],
    this.evidenceId = '',
  });

  final String intersectionId;
  final String dimension;
  final String intersectionClass;
  final String sourceRef;
  final List<String> tagRefs;
  final String evidenceId;
}

/// 导航埋点回调：把命中的 [IntersectionTarget] 与归因透传给展示面（通常接 tracker）。
typedef IntersectionNavTrack =
    void Function(
      IntersectionTarget target,
      IntersectionNavAttribution attribution,
    );

enum IntersectionActionDispatchStatus {
  opened,
  unsupported,
  missingTarget,
  missingRouter,
}

class IntersectionActionDispatchResult {
  const IntersectionActionDispatchResult(this.status);

  final IntersectionActionDispatchStatus status;

  bool get didOpen => status == IntersectionActionDispatchStatus.opened;
}

/// 统一交集导航器（统一交互子契约 · A–E 横切复用）。
///
/// 把云侧 [IntersectionTarget]（objectType + objectId + objectKind + routeId）映射为
/// codegen 路由
/// （[AppRoutePaths]）跳转，端侧不硬编码 path。`routeId` 为云侧「路由逻辑名」闭集
/// （userProfile / circleDetail / homepageDetail / workBrowser / myIntersections），缺省 / 未知时
/// 由 objectKind 经 codegen [intersectionRouteIdForObjectKind]（registry.objectKinds.routeId）
/// 反查；objectKind 不可导航（content/tag/未知）时视为不可点击（返回 null）。
///
/// 不可解析（target 缺省 / objectId 空 / 不可导航 objectKind）时静默不跳转（优雅降级，
/// 不抛错、不崩溃）。埋点经构造时注入的 [onTrack] 透传，导航器本身不依赖 Riverpod，
/// 便于 A–E 复用与组件测试。
class IntersectionTargetNavigator {
  const IntersectionTargetNavigator({this.onTrack});

  final IntersectionNavTrack? onTrack;

  /// 把对象页交集行 [IntersectionReason] 归一为统一导航 [IntersectionTarget]。
  ///
  /// objectKind 一等字段为真相源（旧 relationKind 对象类型桥接已删除，§23 去桥接）；
  /// 交由 [resolvePath] / [open] 经 codegen objectKind→routeId 统一映射。A–E 各展示位
  /// 共用此方法，端不再各自手写 `switch(kind) → context.push(...)` 复制导航逻辑。
  ///
  /// `actionTargetId` 为空时返回空 objectId 的 target，[resolvePath] 据此判定不可路由（优雅降级）。
  static IntersectionTarget targetForReason(IntersectionReason reason) {
    final objectKind = reason.objectKind.trim();
    final routeId = intersectionRouteIdForObjectKind(objectKind);
    return IntersectionTarget(
      objectType: objectTypeForTarget(objectKind: objectKind, routeId: routeId),
      objectId: reason.actionTargetId.trim(),
      objectKind: objectKind,
      routeId: routeId,
    );
  }

  /// 解析 [target] → codegen 路由 path；不可路由返回 null。
  ///
  /// [sourceRef] 仅在下钻「我的交集」维度列表（routeId == myIntersections）时附加证据组过滤。
  static String? resolvePath(
    IntersectionTarget? target, {
    String sourceRef = '',
    String? sourceTheme,
  }) {
    if (target == null) {
      return null;
    }
    final id = target.objectId.trim();
    if (id.isEmpty) {
      return null;
    }
    final ref = sourceRef.trim();
    // routeId 真相源：target.routeId（云侧下发）优先；缺省时由 objectKind 经 codegen
    // 反查（registry.objectKinds.routeId），端不再硬编码 objectKind 闭集与 routeId 兜底 switch。
    var route = target.routeId.trim();
    if (route.isEmpty) {
      route = intersectionRouteIdForObjectKind(target.objectKind.trim());
    }
    switch (route) {
      case 'userProfile':
        return AppRoutePaths.userProfile(userHandle: id);
      case 'circleDetail':
        return AppRoutePaths.circleDetail(id: id, sourceTheme: sourceTheme);
      case 'homepageDetail':
        return AppRoutePaths.homepageDetail(id: id, sourceTheme: sourceTheme);
      case 'workBrowser':
      case 'postDetail':
      case 'contentDetail':
        return AppRoutePaths.workBrowser(workId: id, sourceTheme: sourceTheme);
      case 'myIntersections':
        return AppRoutePaths.myIntersections(
          dimension: id,
          sourceRef: ref.isEmpty ? null : ref,
        );
      default:
        return null;
    }
  }

  /// objectKind + routeId → 导航/埋点用的粗粒度 objectType 桶。
  ///
  /// 上游 objectType 是开放词汇（每个垂类主页一个值），这里只回落到路由能区分的
  /// 少数几个桶；新增垂类由注册表 objectTypeBindings 承接，本方法无需改动。
  static String objectTypeForTarget({
    required String objectKind,
    required String routeId,
  }) {
    switch (routeId.trim()) {
      case 'userProfile':
        return 'user';
      case 'circleDetail':
        return 'circle';
      case 'homepageDetail':
        return 'homepage';
      case 'workBrowser':
      case 'postDetail':
      case 'contentDetail':
        return 'post';
      case 'myIntersections':
        return 'dimension';
    }
    switch (objectKind.trim()) {
      case 'person':
        return 'user';
      case 'circle':
        return 'circle';
      case 'school':
      case 'place':
      case 'enterprise':
      case 'route':
      case 'photo_spot':
      case 'gear':
        return 'homepage';
      case 'content':
        return 'post';
      case 'tag':
        return 'tag';
      default:
        return '';
    }
  }

  /// [target] 是否可点击跳转（用于 UI 决定是否赋予点击态）。
  bool canNavigate(IntersectionTarget? target, {String sourceRef = ''}) =>
      resolvePath(target, sourceRef: sourceRef) != null;

  /// 跳转到 [target] 对应对象页 / 维度列表页；不可路由时静默返回 false（不导航、不上报）。
  bool open(
    BuildContext context,
    IntersectionTarget? target, {
    String sourceRef = '',
    IntersectionNavAttribution? attribution,
  }) {
    final path = resolvePath(
      target,
      sourceRef: sourceRef,
      sourceTheme: uiErrorAppearanceRouteValueFor(context),
    );
    if (path == null || target == null) {
      return false;
    }
    final router = GoRouter.maybeOf(context);
    if (router == null) {
      return false;
    }
    if (attribution != null) {
      onTrack?.call(target, attribution);
    }
    // 圈子承接页进入来源归因：交集语境统一为 myIntersections（强关系探索意图，
    // 区别于推荐流 organicFeed；metadata behaviors.yaml referralSource 闭集语义）。
    var route = target.routeId.trim();
    if (route.isEmpty) {
      route = intersectionRouteIdForObjectKind(target.objectKind.trim());
    }
    if (route == 'circleDetail') {
      router.push(
        path,
        extra: const CircleDetailPageRouteExtra(
          referralSource: ReferralSource.myIntersections,
        ),
      );
      return true;
    }
    router.push(path);
    return true;
  }

  /// 按云侧 actionHint 的 M0.7 `dispatch` 分发行动。
  ///
  /// 本方法只消费 codegen/DTO 字段，不维护第二套 actionKey 分类，也不在本通用交集组件内
  /// 重造多领域写操作与登录续接：
  /// - `assistant`：打开小艺会话（会话页自行处理登录）；
  /// - `navigate`：导航到承接页（userProfile/circleDetail/homepageDetail/我的交集）。
  ///   `requiredGates`（login 等）不在本层拦截——承接页复用既有 gate + AuthContinuation
  ///   续接完成关注 / 加入 / 讨论等写操作（§15 登录入口无死循环），避免在交集组件内
  ///   重造第二套登录逻辑（R24），也避免登录用户看不到行动入口；
  /// - `gathering`：进入既有发起群聊页作为「结伴同行」最薄承接，必须携带
  ///   target/attribution route extra；无对象上下文时不执行，避免退化成普通建群；
  /// - `message`：进入对方主页并直接拉起主页既有的「私信 / 打招呼」分流，陌生人
  ///   走 greeting 破冰状态机；target 非 person 时不执行，不退化成普通对象下钻；
  /// - 未登记 dispatch：fail-closed 返回 unsupported。
  IntersectionActionDispatchResult openActionHint(
    BuildContext context,
    IntersectionActionHint hint, {
    String sourceRef = '',
    IntersectionNavAttribution? attribution,
    IntersectionReason? evidenceReason,
    IntersectionTarget? contextObjectTarget,
  }) {
    switch (hint.dispatch.trim()) {
      case 'assistant':
        return _openAssistant(
          context,
          reason: evidenceReason,
          contextObjectTarget: contextObjectTarget,
        );
      case 'navigate':
        return open(
              context,
              hint.target,
              sourceRef: sourceRef,
              attribution: attribution,
            )
            ? const IntersectionActionDispatchResult(
                IntersectionActionDispatchStatus.opened,
              )
            : const IntersectionActionDispatchResult(
                IntersectionActionDispatchStatus.missingTarget,
              );
      case 'message':
        return _openMessage(context, hint, attribution);
      case 'gathering':
        return _openGathering(context, hint, attribution, evidenceReason);
      default:
        return const IntersectionActionDispatchResult(
          IntersectionActionDispatchStatus.unsupported,
        );
    }
  }

  IntersectionActionDispatchResult _openAssistant(
    BuildContext context, {
    required IntersectionReason? reason,
    required IntersectionTarget? contextObjectTarget,
  }) {
    final router = GoRouter.maybeOf(context);
    if (router == null) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingRouter,
      );
    }
    if (reason == null || contextObjectTarget == null) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingTarget,
      );
    }
    final intersectionId = reason.intersectionId.trim();
    final evidenceId = reason.pointSummarySnapshotId.trim();
    final sourceRef = reason.kind.trim();
    final objectTypeRef = contextObjectTarget.objectType.trim();
    final objectId = contextObjectTarget.objectId.trim();
    if (intersectionId.isEmpty ||
        evidenceId.isEmpty ||
        sourceRef.isEmpty ||
        objectTypeRef.isEmpty ||
        objectId.isEmpty) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingTarget,
      );
    }
    router.push(
      AppRoutePaths.assistantPersonal,
      extra: AssistantOpenContext(
        source: AssistantSource.profile,
        entityId: objectId,
        objectType: objectTypeRef,
        visitTarget: VisitTarget.page(
          'intersection_assistant_${objectTypeRef}_$objectId',
        ),
        experienceLevel: ExperienceLevel.returning,
        intersectionEvidenceRefs: <AssistantIntersectionEvidenceRef>[
          AssistantIntersectionEvidenceRef(
            intersectionId: intersectionId,
            evidenceId: evidenceId,
            sourceRef: sourceRef,
            objectTypeRef: objectTypeRef,
            objectId: objectId,
          ),
        ],
      ),
    );
    return const IntersectionActionDispatchResult(
      IntersectionActionDispatchStatus.opened,
    );
  }

  /// `dispatch: message`（打招呼 / 私信）承接：进入对方主页并直接拉起主页既有的
  /// 「私信 / 打招呼」分流。
  ///
  /// 陌生人走 greeting 破冰（`POST /user/greeting-request`），对方回复后才升级为
  /// 正式会话；能力位、频控、拉黑、登录续接全部由主页实现承接，交集组件不重造
  /// 第二套私信状态机。target 必须是真实 person，否则不执行。
  IntersectionActionDispatchResult _openMessage(
    BuildContext context,
    IntersectionActionHint hint,
    IntersectionNavAttribution? attribution,
  ) {
    final target = hint.target;
    final userId = target?.objectId.trim() ?? '';
    if (target == null || userId.isEmpty || !_isPersonTarget(target)) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingTarget,
      );
    }
    final router = GoRouter.maybeOf(context);
    if (router == null) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingRouter,
      );
    }
    if (attribution != null) {
      onTrack?.call(target, attribution);
    }
    router.push(
      AppRoutePaths.userProfile(userHandle: userId),
      extra: UserProfileRouteExtra(
        personaId: userId,
        openMessageComposer: true,
        greetingIntersectionRef: attribution == null
            ? null
            : GreetingIntersectionRef(
                intersectionId: attribution.intersectionId,
                evidenceId: attribution.evidenceId,
                sourceRef: attribution.sourceRef,
                objectTypeRef: target.objectType.trim(),
                objectId: userId,
              ),
      ),
    );
    return const IntersectionActionDispatchResult(
      IntersectionActionDispatchStatus.opened,
    );
  }

  bool _isPersonTarget(IntersectionTarget target) {
    if (target.objectKind.trim() == 'person') {
      return true;
    }
    if (target.objectType.trim() == 'user') {
      return true;
    }
    return target.routeId.trim() == 'userProfile';
  }

  /// 从云侧主句里取出该 target 的渲染名（如「老君山」）。
  ///
  /// 结伴承接页要用共同对象命名新群，名字必须与用户刚读到的那句话同源：主句 span
  /// 是云侧唯一真相源，端不另查一次对象名，也不用 objectId 冒充名字。
  static String gatheringObjectName(
    IntersectionReason? reason,
    IntersectionTarget target,
  ) {
    final objectId = target.objectId.trim();
    if (reason == null || objectId.isEmpty) {
      return '';
    }
    for (final span in reason.primarySpans) {
      if (span.target?.objectId.trim() != objectId) {
        continue;
      }
      // 主句里的对象名带书名号（云侧 host_plain 合同），群名不需要。
      final text = span.text.trim().replaceAll('「', '').replaceAll('」', '');
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }

  IntersectionActionDispatchResult _openGathering(
    BuildContext context,
    IntersectionActionHint hint,
    IntersectionNavAttribution? attribution,
    IntersectionReason? evidenceReason,
  ) {
    final target = hint.target;
    if (target == null || target.objectId.trim().isEmpty) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingTarget,
      );
    }
    final router = GoRouter.maybeOf(context);
    if (router == null) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingRouter,
      );
    }
    if (attribution != null) {
      onTrack?.call(target, attribution);
    }
    router.push(
      AppRoutePaths.startGroupChat,
      extra: StartGroupChatRouteExtra(
        actionKey: hint.actionKey.trim(),
        actionLabel: hint.label.trim(),
        targetObjectId: target.objectId.trim(),
        targetObjectKind: target.objectKind.trim(),
        targetObjectName: gatheringObjectName(evidenceReason, target),
        targetRouteId: target.routeId.trim(),
        intersectionId: attribution?.intersectionId.trim() ?? '',
        dimension: attribution?.dimension.trim() ?? '',
        intersectionClass: attribution?.intersectionClass.trim() ?? '',
        sourceRef: attribution?.sourceRef.trim() ?? '',
        evidenceId: attribution?.evidenceId.trim() ?? '',
      ),
    );
    return const IntersectionActionDispatchResult(
      IntersectionActionDispatchStatus.opened,
    );
  }
}
