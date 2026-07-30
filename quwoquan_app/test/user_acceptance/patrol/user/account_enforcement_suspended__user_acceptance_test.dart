// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
/// Gamma physical-device UAT: a suspended account rejects its old bearer and
/// the App clears both credentials before exposing the canonical safe surface.
library;

import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show profileQueryProvider;
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import '../../../support/patrol/patrol_account_enforcement_support.dart';
import '../../../support/patrol/patrol_environment_harness.dart';

const _feedbackKey = ValueKey<String>('loginFeedback-loginAccountSuspended');
const _candidateDigest = String.fromEnvironment(
  'QWQ_ACCEPTANCE_CANDIDATE_DIGEST',
);

void main() {
  patrolTest(
    'gamma_suspended_account_rejects_old_session_and_shows_safe_recovery',
    tags: ['t4', 'account-enforcement', 'gamma', 'physical-device'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      expect(
        RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(_candidateDigest),
        isTrue,
        reason: 'the device run must compile against one immutable candidate',
      );
      await launchEnvironmentPatrolApp($);
      final container = await awaitAccountEnforcementContainer($);

      CloudException? authoritativeFailure;
      try {
        await container
            .read(profileQueryProvider(AppUiSurfaces.userProfile))
            .getUserProfile('me');
      } on CloudException catch (error) {
        authoritativeFailure = error;
      }
      expect(
        authoritativeFailure?.code,
        UserErrorCode.accountSuspended.code,
        reason: 'the old bearer must be rejected by canonical User Remote',
      );

      final session = await awaitAccountEnforcementSession(
        $,
        container,
        (state) =>
            state.status == AuthSessionStatus.guest &&
            state.promptReason == AuthPromptReason.accountSuspended,
      );
      expect(
        session.accessToken,
        isEmpty,
        reason: 'access credential must clear',
      );
      expect(
        session.refreshToken,
        isEmpty,
        reason: 'refresh credential must clear',
      );

      final feedback = find.byKey(_feedbackKey);
      expect(
        await waitForAccountEnforcementFinder($, feedback),
        isTrue,
        reason: 'the canonical suspended-account recovery surface must render',
      );
      final feedbackText = feedback.evaluate().single.widget as Text;
      expect(
        <String>{
          UserErrorCode.accountSuspended.defaultMessageZh,
          UserErrorCode.accountSuspended.defaultMessageEn,
        },
        contains(feedbackText.data),
        reason: 'the surface must use generated safe copy',
      );

      // Only non-sensitive boolean/enum evidence is emitted for the runner.
      // ignore: avoid_print
      print(
        'QWQ_ACCOUNT_ENFORCEMENT_EVIDENCE '
        '${jsonEncode(<String, Object>{'phase': 'suspended', 'candidateDigest': _candidateDigest, 'remoteCode': UserErrorCode.accountSuspended.code, 'sessionCredentialsCleared': true, 'restrictionSurfaceVisible': true})}',
      );
    },
  );
}
