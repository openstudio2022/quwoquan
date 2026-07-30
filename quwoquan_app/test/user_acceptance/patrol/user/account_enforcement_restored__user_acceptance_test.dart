// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
/// Gamma physical-device UAT: after formal appeal restoration, a newly issued
/// session reaches User Remote and the safe home surface on the same App build.
library;

import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show profileQueryProvider;
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import '../../../support/patrol/patrol_account_enforcement_support.dart';
import '../../../support/patrol/patrol_environment_harness.dart';

const _homeFirstFrame = ValueKey<String>('home-search-chrome');
const _suspendedFeedback = ValueKey<String>(
  'loginFeedback-loginAccountSuspended',
);
const _candidateDigest = String.fromEnvironment(
  'QWQ_ACCEPTANCE_CANDIDATE_DIGEST',
);

void main() {
  patrolTest(
    'gamma_restored_account_uses_new_session_and_reaches_safe_home',
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
      await container
          .read(profileQueryProvider(AppUiSurfaces.userProfile))
          .getUserProfile('me');

      final session = await awaitAccountEnforcementSession(
        $,
        container,
        (state) =>
            state.status == AuthSessionStatus.authenticated &&
            state.accessToken.trim().isNotEmpty &&
            state.refreshToken.trim().isNotEmpty,
      );
      expect(session.promptReason, isNot(AuthPromptReason.accountSuspended));

      await patrolGoTo($, AppRoutePaths.home);
      expect(
        await waitForAccountEnforcementFinder($, find.byKey(_homeFirstFrame)),
        isTrue,
        reason: 'the restored Remote session must render the safe home surface',
      );
      expect(find.byKey(_suspendedFeedback), findsNothing);

      // Only non-sensitive boolean evidence is emitted for the runner.
      // ignore: avoid_print
      print(
        'QWQ_ACCOUNT_ENFORCEMENT_EVIDENCE '
        '${jsonEncode(<String, Object>{'phase': 'restored', 'candidateDigest': _candidateDigest, 'remoteProfileRead': true, 'sessionAuthenticated': true, 'safeHomeVisible': true})}',
      );
    },
  );
}
