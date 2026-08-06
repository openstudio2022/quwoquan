/// Account-enforcement physical-device UAT support.
///
/// Only exposes read-only access to the mounted production composition. The
/// actual auth state and ProfileQuery remain owned by the App composition.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';

Future<ProviderContainer> awaitAccountEnforcementContainer(
  PatrolIntegrationTester $, {
  Duration timeout = const Duration(seconds: 20),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final element in find.byType(Navigator).evaluate()) {
      try {
        final container = ProviderScope.containerOf(element);
        container.read(authSessionControllerProvider);
        return container;
      } catch (_) {
        // Overlay navigators do not necessarily own the business ProviderScope.
      }
    }
    await $.pump(const Duration(milliseconds: 300));
  }
  throw StateError(
    'account-enforcement UAT cannot locate the App ProviderScope',
  );
}

Future<AuthSessionState> awaitAccountEnforcementSession(
  PatrolIntegrationTester $,
  ProviderContainer container,
  bool Function(AuthSessionState state) predicate, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    final session = container.read(authSessionControllerProvider);
    if (predicate(session)) return session;
    await $.pump(const Duration(milliseconds: 300));
  }
  final session = container.read(authSessionControllerProvider);
  throw StateError(
    'account-enforcement session did not reach its required state: '
    '${session.status.name}/${session.promptReason?.name ?? 'none'}',
  );
}

Future<bool> waitForAccountEnforcementFinder(
  PatrolIntegrationTester $,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 300));
  }
  return finder.evaluate().isNotEmpty;
}
