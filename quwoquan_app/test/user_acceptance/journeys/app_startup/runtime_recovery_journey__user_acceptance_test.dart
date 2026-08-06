// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md#gwt-002
/// Patrol UAT：真实设备持久化登录态下的一次性根容器恢复与防循环。
///
/// 本用例不注入 AuthSessionController。执行设备必须预先通过正式 Remote 登录，
/// 由产品代码从 secure storage 恢复会话；根容器重建后再次读取同一持久化会话。
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/recovery/runtime_recovery_host.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

const _homeFirstFrame = ValueKey<String>('home-search-chrome');

void main() {
  patrolTest(
    'runtime_recovery_restores_persisted_session_once_and_never_loops',
    tags: ['user-acceptance', 'runtime-recovery', 'physical-device'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppWithPersistedSessionOnce($);
      final before = await _awaitAuthenticatedSession($);
      await patrolGoTo($, AppRoutePaths.home);
      expect(
        await _waitForFinder($, find.byKey(_homeFirstFrame)),
        isTrue,
        reason: '根故障注入前必须已渲染 production Remote 首页首帧',
      );

      RuntimeRecoveryCoordinator.instance.enter(
        error: const UnrecoverableRuntimeException(
          cause: 'patrol-controlled-root-fault',
          source: 'runtime_recovery_physical_device_uat',
        ),
        stack: StackTrace.current,
        source: 'runtime_recovery_physical_device_uat',
      );
      await $.pump();
      expect(find.text(FoundationText.runtimeRecoveryTitle), findsOneWidget);
      expect(find.text(FoundationText.runtimeRecoveryAction), findsOneWidget);

      await $.tester.tap(find.text(FoundationText.runtimeRecoveryAction));
      await $.pump();
      expect(
        find.text(FoundationText.runtimeRecoveryEnteringTitle),
        findsOneWidget,
      );
      expect(
        await _waitForFinder(
          $,
          find.byKey(_homeFirstFrame),
          timeout: const Duration(seconds: 30),
        ),
        isTrue,
        reason: '一次性主容器重建后必须返回首页首帧',
      );
      expect(
        await _waitForAbsence(
          $,
          find.text(FoundationText.runtimeRecoveryTitle),
          timeout: const Duration(seconds: 30),
        ),
        isTrue,
        reason: '安全 Shell 就绪后必须移除恢复页且不可返回',
      );

      final after = await _awaitAuthenticatedSession($);
      expect(after.ownerId, before.ownerId, reason: '根容器重建不得切换账号');
      expect(
        after.activePersonaId,
        before.activePersonaId,
        reason: '根容器重建不得切换 Persona',
      );

      RuntimeRecoveryCoordinator.instance.enter(
        error: const UnrecoverableRuntimeException(
          cause: 'patrol-controlled-second-root-fault',
          source: 'runtime_recovery_physical_device_uat_second_fault',
        ),
        stack: StackTrace.current,
        source: 'runtime_recovery_physical_device_uat_second_fault',
      );
      await $.pump();
      expect(find.text(FoundationText.runtimeRecoveryTitle), findsOneWidget);
      expect(
        find.text(FoundationText.runtimeRecoveryAction),
        findsNothing,
        reason: '同一进程第二次根故障必须直接进入 R3，禁止恢复循环',
      );

      // 只输出布尔验收事实，不泄露 owner/persona/token。
      // ignore: avoid_print
      print(
        'QWQ_RUNTIME_RECOVERY_EVIDENCE '
        '${jsonEncode(<String, bool>{'authenticatedBefore': before.isAuthenticated, 'authenticatedAfter': after.isAuthenticated, 'sameOwner': after.ownerId == before.ownerId, 'samePersona': after.activePersonaId == before.activePersonaId, 'homeRestored': true, 'secondFaultNoReentry': true})}',
      );
    },
  );
}

Future<AuthSessionState> _awaitAuthenticatedSession(
  PatrolIntegrationTester $, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final element in find.byType(Navigator).evaluate()) {
      try {
        final session = ProviderScope.containerOf(
          element,
        ).read(authSessionControllerProvider);
        if (session.isAuthenticated &&
            session.ownerId.trim().isNotEmpty &&
            session.activePersonaId.trim().isNotEmpty) {
          return session;
        }
      } catch (_) {
        // Recovery overlay has its own Navigator without the business scope.
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  throw StateError(
    'runtime recovery UAT requires a real persisted authenticated session',
  );
}

Future<bool> _waitForFinder(
  PatrolIntegrationTester $,
  Finder finder, {
  Duration timeout = const Duration(seconds: 20),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 300));
  }
  return finder.evaluate().isNotEmpty;
}

Future<bool> _waitForAbsence(
  PatrolIntegrationTester $,
  Finder finder, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isEmpty) return true;
    await $.pump(const Duration(milliseconds: 300));
  }
  return finder.evaluate().isEmpty;
}
