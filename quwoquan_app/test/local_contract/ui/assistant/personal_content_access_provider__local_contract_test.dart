import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

class _FakeAssistantConsentFacet implements AssistantSkillConsentFacet {
  _FakeAssistantConsentFacet({List<SkillConsent>? initial})
    : _items = <SkillConsent>[...?initial];

  final List<SkillConsent> _items;

  @override
  Future<List<SkillConsent>> listConsents() async {
    return List<SkillConsent>.from(_items);
  }

  @override
  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  }) async {
    _items.removeWhere((item) => item.skillId == skillId);
    final next = _consent(
      skillId: skillId,
      grantedScopes: grantedScopes,
      grantedAt: DateTime.utc(2026, 3, 12, 10, 0),
    );
    _items.add(next);
    return next;
  }

  @override
  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  }) async {
    _items.removeWhere((item) => item.skillId == skillId);
  }
}

SkillConsent _consent({
  required String skillId,
  required List<String> grantedScopes,
  required DateTime grantedAt,
}) {
  return SkillConsent(
    id: 'consent:$skillId',
    accountId: 'account-1',
    skillId: skillId,
    grantedScopes: grantedScopes,
    grantedAt: grantedAt.toUtc().toIso8601String(),
    revokedAt: null,
    granted: true,
  );
}

void main() {
  test('hydrate existing personal_content_access consent', () async {
    final container = ProviderContainer(
      overrides: [
        assistantSkillConsentFacetProvider.overrideWithValue(
          _FakeAssistantConsentFacet(
            initial: <SkillConsent>[
              _consent(
                skillId: kPersonalContentAccessSkillId,
                grantedScopes: const <String>[kPersonalContentAccessScope],
                grantedAt: DateTime.utc(2026, 3, 12, 9, 0),
              ),
            ],
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(personalContentAccessProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final state = container.read(personalContentAccessProvider);
    expect(state.granted, isTrue);
    expect(state.summaryLabel, '已允许');
    expect(state.isHydrating, isFalse);
  });

  test(
    'grant and revoke drive assistant identity index consumer flag',
    () async {
      final container = ProviderContainer(
        overrides: [
          assistantSkillConsentFacetProvider.overrideWithValue(
            _FakeAssistantConsentFacet(),
          ),
          contentFeatureFlagProvider(
            'enable_assistant_content_identity_index',
          ).overrideWithValue(true),
        ],
      );
      addTearDown(container.dispose);

      container.read(personalContentAccessProvider);
      await Future<void>.delayed(const Duration(milliseconds: 1));
      expect(
        container.read(assistantPersonalContentAccessGrantedProvider),
        isFalse,
      );
      expect(
        container.read(assistantContentIdentityIndexEnabledProvider),
        isFalse,
      );

      await container
          .read(personalContentAccessProvider.notifier)
          .setGranted(true);

      expect(
        container.read(assistantPersonalContentAccessGrantedProvider),
        isTrue,
      );
      expect(
        container.read(assistantContentIdentityIndexEnabledProvider),
        isTrue,
      );

      await container
          .read(personalContentAccessProvider.notifier)
          .setGranted(false);

      expect(
        container.read(assistantPersonalContentAccessGrantedProvider),
        isFalse,
      );
      expect(
        container.read(assistantContentIdentityIndexEnabledProvider),
        isFalse,
      );
    },
  );
}
