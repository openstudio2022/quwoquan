// 圈子端侧数据边界：已展示服务端确认快照后，成员请求失败必须保留可识别快照
// 与恢复动作，不得注入 Mock 成员/动态或伪造成功。
// spec_ref: specs/feature-tree/circle-community/circle-client-platform/circle-client-boundary/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-client-platform/circle-client-boundary/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/circle-client-platform/spec.md#sit-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/circle_shell_presentation_slots.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_membership_errors.g.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_shell.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/application/public/circle_behavior_fact_appender.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_engagement_tracker.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/circle_service/circle_management/circle/typed_circle_query_test_double.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

const String _circleId = 'circle-boundary-snapshot';
const String _circleName = '边界快照圈';

class _NoopCircleBehaviorFactWriter implements CircleBehaviorFactAppender {
  const _NoopCircleBehaviorFactWriter();

  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {}
}

final class _FailingMembershipQuery implements CircleMembershipQueries {
  const _FailingMembershipQuery();

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) async => throw _membershipStorageException();

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async => throw _membershipStorageException();

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) async => throw _membershipStorageException();
}

CloudException _membershipStorageException() {
  const errorCode = CircleMembershipErrorCode.membershipStorageWriteFailed;
  return CloudException(
    type: CloudErrorType.server,
    message: errorCode.code,
    statusCode: errorCode.httpStatus,
    code: errorCode.code,
    domainErrorCode: DomainErrorCodeRegistry.fromCode(errorCode.code),
    runtimeFailure: RuntimeFailure(
      code: errorCode.code,
      semanticReason: 'membership_storage_write_failed',
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.internal,
      nature: RuntimeFailureNature.transient,
      location: const RuntimeFailureLocation(
        businessObject: 'circle.circle_membership',
        functionModule: 'circle_client_boundary_test',
      ),
      context: const RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[],
      ),
      recovery: const RuntimeRecoveryDirective.none(),
    ),
    userMessage: errorCode.defaultMessage,
  );
}

Widget _scopedApp() {
  final query = CircleQueryReaderTestDouble(
    get: (CircleDetailQuery detail) => buildCircleTestDoubleFixture(
      detail.circleId,
      name: _circleName,
      memberCount: 12,
    ),
  );
  final visitRecorderService = VisitRecorderService();
  final behaviorRepository = RecordingContentBehaviorRepository();
  final contentEngagementTracker = ContentEngagementTracker(
    reporter: behaviorRepository,
  );
  const writer = _NoopCircleBehaviorFactWriter();
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      visitRecorderServiceProvider.overrideWithValue(visitRecorderService),
      circleDetailQueryProvider.overrideWithValue(query),
      circleDetailFeedQueryProvider.overrideWithValue(query),
      circlesListQueryProvider.overrideWithValue(query),
      circleDetailMembershipQueryProvider.overrideWithValue(
        const _FailingMembershipQuery(),
      ),
      resolvedOwnerUserIdProvider.overrideWithValue('user_001'),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'user_001',
          ownerUserId: 'user_001',
          displayName: '边界测试用户',
          avatarUrl: '',
          contextVersion: 1,
        ),
      ),
      circleDetailBehaviorFactWriterProvider.overrideWithValue(writer),
      behaviorRepositoryProvider.overrideWithValue(behaviorRepository),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: CircleDetailPage(
          circleId: _circleId,
          onBack: () {},
          visitRecorderService: visitRecorderService,
          contentEngagementTracker: contentEngagementTracker,
          hasAuthenticatedOwner: true,
          behaviorFactAppender: writer,
          participantSlots: buildCircleShellParticipantSlots(
            membershipApprovalPageBuilder: (_) => const SizedBox.shrink(),
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('圈子快照已展示后成员请求失败保留快照与恢复面且不注入 Mock', (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_scopedApp());
    await tester.pumpAndSettle();

    expect(find.byType(CircleShell), findsOneWidget);
    expect(find.text(_circleName), findsWidgets);
    expect(find.byType(AppSectionErrorCard), findsWidgets);
    expect(find.textContaining('Mock'), findsNothing);
    expect(find.textContaining('mock'), findsNothing);
    expect(find.text('fixture_persona'), findsNothing);
  });
}
