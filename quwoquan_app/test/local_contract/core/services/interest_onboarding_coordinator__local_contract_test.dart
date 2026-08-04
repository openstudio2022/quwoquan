// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/content/content/post/application/interest_onboarding.dart';
import 'package:quwoquan_app/infrastructure/local/onboarding/secure_interest_onboarding_draft_store.dart';

void main() {
  group('InterestOnboardingCoordinator', () {
    test(
      'keeps one stable intent across failed confirmation and retry',
      () async {
        final store = _MemoryStore();
        final writer = _RecordingWriter(failFirst: true);
        final coordinator = InterestOnboardingCoordinator(
          draftStore: store,
          writer: writer,
        );

        final selected = await coordinator.select(
          taxonomyReleaseId: ' tag-taxonomy-current ',
          tagRefs: const <String>[
            'Topic/兴趣/旅行',
            'Topic/兴趣/旅行',
            'Audience/用户/兴趣偏好/摄影',
          ],
        );
        expect(selected.tagRefs, <String>[
          'Topic/兴趣/旅行',
          'Audience/用户/兴趣偏好/摄影',
        ]);

        await expectLater(
          coordinator.submit(selected),
          throwsA(isA<StateError>()),
        );
        expect((await store.read())!.status, InterestOnboardingStatus.pending);

        final submitted = await coordinator.submit((await store.read())!);
        expect(submitted.status, InterestOnboardingStatus.submitted);
        expect(writer.clientEventIds, <String>[
          selected.clientEventId,
          selected.clientEventId,
        ]);
        expect(writer.taxonomyReleaseIds, <String>[
          'tag-taxonomy-current',
          'tag-taxonomy-current',
        ]);
      },
    );

    test('skip does not fabricate a submission', () async {
      final store = _MemoryStore();
      final writer = _RecordingWriter();
      final coordinator = InterestOnboardingCoordinator(
        draftStore: store,
        writer: writer,
      );

      final skipped = await coordinator.skip(
        taxonomyReleaseId: 'tag-taxonomy-current',
      );

      expect(skipped.status, InterestOnboardingStatus.skipped);
      expect(skipped.tagRefs, isEmpty);
      expect(writer.clientEventIds, isEmpty);
    });

    test('reuses a restored continuation client event id', () async {
      final store = _MemoryStore();
      final coordinator = InterestOnboardingCoordinator(
        draftStore: store,
        writer: _RecordingWriter(),
      );
      const restored = InterestOnboardingDraft(
        taxonomyReleaseId: 'tag-taxonomy-current',
        clientEventId: 'onboarding:stable-intent',
        tagRefs: <String>['Topic/兴趣/旅行'],
        status: InterestOnboardingStatus.unseen,
      );

      final selected = await coordinator.select(
        taxonomyReleaseId: restored.taxonomyReleaseId,
        tagRefs: restored.tagRefs,
        previous: restored,
      );

      expect(selected.clientEventId, restored.clientEventId);
      expect((await store.read())!.clientEventId, restored.clientEventId);
    });

    test(
      'does not reuse an intent across taxonomy snapshot releases',
      () async {
        final store = _MemoryStore();
        final coordinator = InterestOnboardingCoordinator(
          draftStore: store,
          writer: _RecordingWriter(),
        );
        const previous = InterestOnboardingDraft(
          taxonomyReleaseId: 'tag-taxonomy-old',
          clientEventId: 'onboarding:old-release-intent',
          tagRefs: <String>['Topic/兴趣/旅行'],
          status: InterestOnboardingStatus.pending,
        );

        final selected = await coordinator.select(
          taxonomyReleaseId: 'tag-taxonomy-current',
          tagRefs: previous.tagRefs,
          previous: previous,
        );

        expect(selected.clientEventId, isNot(previous.clientEventId));
        expect(selected.taxonomyReleaseId, 'tag-taxonomy-current');
      },
    );

    test('rejects unknown draft fields instead of guessing a second shape', () {
      final parsed = InterestOnboardingDraft.tryParse(<String, Object?>{
        'unexpectedEnvelopeField': 'retired',
        'taxonomyReleaseId': 'tag-taxonomy-current',
        'clientEventId': 'onboarding:retired-draft',
        'tagRefs': <String>['Topic/兴趣/旅行'],
        'status': 'pending',
      });

      expect(parsed, isNull);
    });

    test('persists only the canonical taxonomy release identity', () {
      const draft = InterestOnboardingDraft(
        taxonomyReleaseId: 'tag-taxonomy-current',
        clientEventId: 'onboarding:canonical-draft',
        tagRefs: <String>['Topic/兴趣/旅行'],
        status: InterestOnboardingStatus.pending,
      );

      expect(draft.toJson().keys, <String>[
        'taxonomyReleaseId',
        'clientEventId',
        'tagRefs',
        'status',
      ]);
      expect(InterestOnboardingDraft.tryParse(draft.toJson()), isNotNull);
    });

    test('账号 closed 终态清除加密兴趣草稿并读回验证', () async {
      FlutterSecureStorage.setMockInitialValues(<String, String>{});
      const store = SecureInterestOnboardingDraftStore();
      const draft = InterestOnboardingDraft(
        taxonomyReleaseId: 'tag-taxonomy-current',
        clientEventId: 'onboarding:closed',
        tagRefs: <String>['Topic/兴趣/旅行'],
        status: InterestOnboardingStatus.pending,
      );
      await store.write(draft);
      expect(await store.read(), isNotNull);

      await store.clearForTerminalAccountClosure();

      expect(await store.read(), isNull);
    });
  });
}

final class _MemoryStore implements InterestOnboardingDraftStore {
  InterestOnboardingDraft? draft;

  @override
  Future<InterestOnboardingDraft?> read() async => draft;

  @override
  Future<void> write(InterestOnboardingDraft next) async {
    draft = next;
  }
}

final class _RecordingWriter implements ConfirmedOnboardingInterestWriter {
  _RecordingWriter({this.failFirst = false});

  final bool failFirst;
  final List<String> clientEventIds = <String>[];
  final List<String> taxonomyReleaseIds = <String>[];

  @override
  Future<void> submit({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    clientEventIds.add(clientEventId);
    taxonomyReleaseIds.add(taxonomyReleaseId);
    if (failFirst && clientEventIds.length == 1) {
      throw StateError('offline');
    }
  }
}
