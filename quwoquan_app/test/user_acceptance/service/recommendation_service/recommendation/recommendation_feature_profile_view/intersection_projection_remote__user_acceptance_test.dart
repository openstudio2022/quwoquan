// readiness_case: intersection_projection_app_uat
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/user-profile-intersection-redesign/spec.md#gwt-004
/// viewer 通过公开 User command 关注 disposable actor；actor 再经公开 Content
/// command 发布 Post 并写入行为事实。Recommendation 只能从这些真实事件 materialize
/// typed intersection，production App 离页重入后必须仍从 Remote 读回同一 identity。
///
/// 当前 Gamma 尚无受治理的 selective projection failure、访问水位失败与同一 candidate
/// Android+iPhone ResultBundle，因此本 source runner 不登记 readiness_case。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/recommendation_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _disposableActorsConfirmed = bool.fromEnvironment(
  'QWQ_RECOMMENDATION_INTERSECTION_DISPOSABLE_ACTORS_ACK',
);

void main() {
  patrolTest(
    'recommendation_remote_materializes_and_reloads_my_intersection',
    tags: const ['user-acceptance', 'home-rec', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      RecommendationApiContractHarness? recommendationHarness;
      UserApiContractHarness? relationshipHarness;
      ContentApiContractHarness? actorHarness;
      String? postId;

      try {
        recommendationHarness = await RecommendationApiContractHarness.create();
        relationshipHarness = await UserApiContractHarness.create();
        actorHarness = await ContentApiContractHarness.create();

        final viewer = recommendationHarness.session;
        final viewerPersonaId = viewer.activePersona?.personaId.trim() ?? '';
        final actorPersonaId =
            actorHarness.session.activePersona?.personaId.trim() ?? '';
        if (viewerPersonaId.isEmpty || actorPersonaId.isEmpty) {
          throw StateError('Disposable actors require active personas');
        }

        final title = '真实交集行为 $suffix';
        final publication = await actorHarness.publication
            .submitPostPublication(
              SubmitContentPostPublicationCommand(
                publishIntentId: 'intersection-post-$suffix',
                localDraftId: 'intersection-post-draft-$suffix',
                contentType: ContentType.micro,
                contentIdentity: ContentIdentity.moment,
                title: title,
                body: '$title 只经公开 Content command 写入',
                visibility: Visibility.public,
              ),
            );
        postId = publication.postId.trim();
        if (postId.isEmpty) {
          throw StateError('SubmitPostPublication returned an empty postId');
        }

        await relationshipHarness.withSession(
          session: viewer,
          action: () => relationshipHarness!.withIdempotencyKey(
            idempotencyKey: 'intersection-follow-$suffix',
            action: () =>
                relationshipHarness!.personaRelationshipFollows.follow(
                  actorPersonaId,
                  sourceSurfaceId: AppUiSurfaces.userProfile.id,
                ),
          ),
        );
        final capability = await relationshipHarness.withSession(
          session: viewer,
          action: () => relationshipHarness!.personaRelationships
              .getRelationshipCapability(
                GetRelationshipCapabilityQuery(targetPersonaId: actorPersonaId),
              ),
        );
        if (capability.relationState != RelationshipState.following &&
            capability.relationState != RelationshipState.mutual) {
          throw StateError('FollowUser did not converge before projection');
        }

        await actorHarness.behaviors.reportBehaviors(
          ReportContentBehaviorsCommand(
            events: <ContentBehaviorEventWire>[
              ContentBehaviorEventWire(
                clientEventId: 'intersection-behavior-$suffix',
                occurredAt: DateTime.now().toUtc(),
                contentId: postId,
                action: BehaviorEventType.click,
                state: 'click',
                contentType: ContentType.micro,
                objectId: postId,
                objectKind: 'post',
                displayName: title,
              ),
            ],
          ),
        );

        final reason = await _waitForCanonicalIntersection(
          recommendationHarness,
          postId: postId,
          title: title,
        );
        installPatrolAcceptanceSessionForRunner(
          accessToken: viewer.accessToken,
          refreshToken: viewer.refreshToken,
          ownerId: viewer.ownerId,
          personaId: viewerPersonaId,
        );
        await launchPatrolAppOnce($);

        await _openMyIntersections($, primaryText: reason.primaryText);
        await patrolGoTo($, AppRoutePaths.home);
        await _openMyIntersections($, primaryText: reason.primaryText);

        final remoteReadback = await recommendationHarness.intersections
            .listMyIntersections(filter: 'fact', limit: 50);
        expect(
          remoteReadback.where(
            (item) =>
                item.intersectionId == reason.intersectionId &&
                item.actionTargetId == postId,
          ),
          hasLength(1),
        );
      } finally {
        try {
          if (postId != null && actorHarness != null) {
            await actorHarness.postDeletion.deletePost(
              postId: postId,
              idempotencyKey: 'intersection-post-cleanup-$suffix',
            );
          }
        } finally {
          try {
            await actorHarness?.close();
          } finally {
            try {
              await relationshipHarness?.close();
            } finally {
              await recommendationHarness?.close();
            }
          }
        }
      }
    },
  );
}

Future<IntersectionReason> _waitForCanonicalIntersection(
  RecommendationApiContractHarness harness, {
  required String postId,
  required String title,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 90));
  while (DateTime.now().isBefore(deadline)) {
    final reasons = await harness.intersections.listMyIntersections(
      filter: 'fact',
      limit: 50,
    );
    for (final reason in reasons) {
      if (reason.actionTargetId == postId &&
          reason.intersectionClass == 'fact' &&
          reason.primaryText.contains(title)) {
        return reason;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 500));
  }
  throw StateError(
    'Recommendation projection did not materialize the public behavior fact',
  );
}

Future<void> _openMyIntersections(
  PatrolIntegrationTester $, {
  required String primaryText,
}) async {
  await patrolGoTo($, AppRoutePaths.myIntersections(filter: 'fact'));
  await $(find.byType(MyIntersectionInboxPage)).waitUntilVisible();
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      fail('production MyIntersections entered an error terminal');
    }
    if (find.text(primaryText).evaluate().isNotEmpty) {
      expect(find.text(primaryText), findsOneWidget);
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('production MyIntersections did not render the canonical projection');
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Recommendation intersection UAT requires matching gamma APP_RUNTIME_ENV '
      'and API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'Recommendation intersection UAT installs its own disposable session',
    );
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'Recommendation intersection UAT requires absolute HTTPS gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'Recommendation intersection UAT requires one App/API gateway',
    );
  }
  if (!_disposableActorsConfirmed) {
    throw StateError(
      'Set QWQ_RECOMMENDATION_INTERSECTION_DISPOSABLE_ACTORS_ACK=true only '
      'when Post deletion and account closure are permitted',
    );
  }
}

bool _isAbsoluteHttps(Uri? value) =>
    value != null &&
    value.isAbsolute &&
    value.scheme == 'https' &&
    value.host.isNotEmpty;

String _normalizedGateway(Uri value) {
  final path = value.path.replaceFirst(RegExp(r'/+$'), '');
  return value.replace(path: path, query: null, fragment: null).toString();
}
