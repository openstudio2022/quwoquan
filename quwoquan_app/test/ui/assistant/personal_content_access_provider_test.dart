import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

class _FakeAssistantRepository implements AssistantRepository {
  _FakeAssistantRepository({List<AssistantSkillConsent>? initial})
    : _items = <AssistantSkillConsent>[...?initial];

  final List<AssistantSkillConsent> _items;

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    return List<AssistantSkillConsent>.from(_items);
  }

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    _items.removeWhere((item) => item.skillId == skillId);
    final next = AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime.utc(2026, 3, 12, 10, 0),
    );
    _items.add(next);
    return next;
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) async {
    _items.removeWhere((item) => item.skillId == skillId);
  }

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
  }) async {
    return AssistantSearchResultView(
      queryEcho: query,
      searchIntensity: searchIntensity,
    );
  }
}

void main() {
  test('hydrate existing personal_content_access consent', () async {
    final container = ProviderContainer(
      overrides: [
        assistantRepositoryProvider.overrideWithValue(
          _FakeAssistantRepository(
            initial: <AssistantSkillConsent>[
              AssistantSkillConsent(
                skillId: kPersonalContentAccessSkillId,
                grantedScope: kPersonalContentAccessSkillId,
                granted: true,
                updatedAt: DateTime.utc(2026, 3, 12, 9, 0),
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
          assistantRepositoryProvider.overrideWithValue(
            _FakeAssistantRepository(),
          ),
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
