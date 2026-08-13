// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-001
// readiness_case: profile_interaction_projection_app_uat
/// Patrol UAT：我的主页的互动页经 production Remote 读取真实投影。
///
/// create-then-readback：先经公开 Content command 创建真实 Post 与评论互动，
/// 再断言互动 Tab 渲染该互动事实。空态不再是本用例的合法终态——防止
/// 「环境无数据时空页也算通过」；无互动 Persona 的空态语义由 local_contract
/// 层两态用例承载。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    'my_profile_interaction_tab_renders_created_interaction',
    tags: ['user-acceptance', 'content', 'user-profile'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
      );
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final commentBody = '互动投影验收评论 $suffix';
      final harness = await ContentApiContractHarness.create();
      String? postId;
      try {
        // 前置互动事实只经公开 command：同一 disposable actor 发 Post 并评论。
        final publication = await harness.publication.submitPostPublication(
          SubmitContentPostPublicationCommand(
            publishIntentId: 'profile-interaction-uat-$suffix',
            localDraftId: 'profile-interaction-uat-draft-$suffix',
            contentType: ContentType.micro,
            contentIdentity: ContentIdentity.moment,
            body: '互动投影验收对象 $suffix',
            visibility: Visibility.public,
          ),
        );
        postId = publication.postId;
        expect(postId.trim(), isNotEmpty, reason: 'publication must return postId');
        await harness.comments.createComment(
          CreateContentCommentCommand(postId: postId, content: commentBody),
        );

        final session = harness.session;
        final personaId = session.activePersona?.personaId.trim() ?? '';
        expect(personaId, isNotEmpty, reason: 'disposable actor needs persona');
        installPatrolAcceptanceSessionForRunner(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          ownerId: session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);
        await patrolGoTo($, AppRoutePaths.profile);

        await $(
          find.text(ProfileText.profileTabInteraction),
        ).waitUntilVisible(timeout: const Duration(seconds: 20));
        await $(find.text(ProfileText.profileTabInteraction)).tap();

        final rendered = await _waitForCreatedInteraction($, commentBody);
        expect(
          rendered,
          isTrue,
          reason:
              'interaction tab must render the interaction created through the '
              'public command; an empty page is not a legal terminal here',
        );
      } finally {
        try {
          if (postId != null) {
            await harness.postDeletion.deletePost(
              postId: postId,
              idempotencyKey: 'profile-interaction-uat-cleanup-$suffix',
            );
          }
        } finally {
          await harness.close();
        }
      }
    },
  );
}

/// 只接受真实互动行渲染（评论正文出现）；空态标题不构成通过条件。
Future<bool> _waitForCreatedInteraction(
  PatrolIntegrationTester $,
  String commentBody,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 25));
  while (DateTime.now().isBefore(deadline)) {
    if (find.textContaining(commentBody).evaluate().isNotEmpty) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
