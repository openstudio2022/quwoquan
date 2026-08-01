import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_resolve_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/career_interest_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('职业与兴趣页未保存返回使用 iOS alert 确认', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileEditQueryProvider.overrideWith(
            (ref, surface) => const _CareerProfileEditQuery(),
          ),
          tagCatalogQueryProvider.overrideWithValue(AlphaTagFacet()),
          tagFeedbackCommandWriterProvider.overrideWithValue(
            AlphaTagFeedbackWriter(),
          ),
        ],
        child: const MaterialApp(home: _CareerInterestHost()),
      ),
    );

    await tester.tap(find.text('打开职业与兴趣'));
    await tester.pumpAndSettle();

    expect(find.text(ProfileText.careerInterestTitle), findsOneWidget);
    await tester.tap(find.text('旅行').first);
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.byIcon(CupertinoIcons.back));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    expect(find.text(ProfileText.careerInterestUnsavedTitle), findsOneWidget);
    expect(find.text(ProfileText.careerInterestUnsavedMessage), findsOneWidget);
    final dialog = find.byType(CupertinoAlertDialog);
    expect(
      find.descendant(
        of: dialog,
        matching: find.text(ProfileText.editProfileSaveAction),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: dialog,
        matching: find.text(ProfileText.careerInterestKeepEditing),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: dialog,
        matching: find.text(ProfileText.careerInterestDiscard),
      ),
      findsOneWidget,
    );

    await tester.tap(
      find.descendant(
        of: dialog,
        matching: find.text(ProfileText.careerInterestKeepEditing),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(CupertinoAlertDialog), findsNothing);
    expect(find.text(ProfileText.careerInterestTitle), findsOneWidget);
  });

  testWidgets('销毁带摇摆标签的职业与兴趣页不会抛异常', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileEditQueryProvider.overrideWith(
            (ref, surface) => const _CareerProfileEditQuery(),
          ),
          tagCatalogQueryProvider.overrideWithValue(AlphaTagFacet()),
          tagFeedbackCommandWriterProvider.overrideWithValue(
            AlphaTagFeedbackWriter(),
          ),
        ],
        child: const MaterialApp(home: _CareerInterestHost()),
      ),
    );

    await tester.tap(find.text('打开职业与兴趣'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('旅行').first);
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.byIcon(CupertinoIcons.back));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text(ProfileText.careerInterestDiscard));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text(ProfileText.careerInterestTitle), findsNothing);
    expect(find.text('打开职业与兴趣'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('保存命令使用 Remote 目录返回的 taxonomy release 前置条件', (tester) async {
    const remoteReleaseId = 'taxonomy-release-from-remote';
    final writer = _CapturingProfileCommandWriter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileEditQueryProvider.overrideWith(
            (ref, surface) => const _CareerProfileEditQuery(),
          ),
          tagCatalogQueryProvider.overrideWithValue(
            _ReleaseOverrideTagCatalogQuery(remoteReleaseId),
          ),
          tagFeedbackCommandWriterProvider.overrideWithValue(
            AlphaTagFeedbackWriter(),
          ),
          profileCommandWriterProvider.overrideWithValue(writer),
        ],
        child: const MaterialApp(home: _CareerInterestHost()),
      ),
    );

    await tester.tap(find.text('打开职业与兴趣'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('旅行').first);
    await tester.pump(const Duration(milliseconds: 200));
    await tester.tap(find.text(ProfileText.editProfileSaveAction));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(writer.command, isNotNull);
    expect(writer.command!.expectedTaxonomyReleaseId, remoteReleaseId);
    expect(writer.command!.interestTagRefs, isNotEmpty);
    await tester.pump(const Duration(seconds: 4));
  });
}

final class _CapturingProfileCommandWriter implements ProfileCommandWriter {
  UpdateUserProfileCommand? command;

  @override
  Future<ProfileUpdateSnapshot> updateUserProfile(
    UpdateUserProfileCommand command,
  ) async {
    this.command = command;
    return const ProfileUpdateSnapshot(
      userId: 'owner-1',
      nickname: '测试用户',
      nicknameCustomized: true,
      profileVersion: 2,
    );
  }
}

final class _ReleaseOverrideTagCatalogQuery implements TagCatalogQuery {
  _ReleaseOverrideTagCatalogQuery(this.releaseId) : _inner = AlphaTagFacet();

  final String releaseId;
  final AlphaTagFacet _inner;

  @override
  Future<List<TagChild>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    final children = await _inner.listChildren(parentTagRef, limit: limit);
    return <TagChild>[
      for (final child in children)
        TagChild(
          tagRef: child.tagRef,
          label: child.label,
          displayLabel: child.displayLabel,
          labelEn: child.labelEn,
          parentTagRef: child.parentTagRef,
          depth: child.depth,
          hasChildren: child.hasChildren,
          releaseId: releaseId,
          lifecycleStatus: child.lifecycleStatus,
        ),
    ];
  }

  @override
  Future<TagResolve> resolveTag(String tagRef) => _inner.resolveTag(tagRef);

  @override
  Future<TagValidationResult> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    if (expectedTaxonomyReleaseId != releaseId) {
      return TagValidationResult(
        taxonomyReleaseId: releaseId,
        valid: const <String>[],
        invalid: tagRefs,
      );
    }
    final innerResult = await _inner.validateRefs(
      expectedTaxonomyReleaseId: _inner.taxonomyReleaseId,
      tagRefs: tagRefs,
    );
    return TagValidationResult(
      taxonomyReleaseId: releaseId,
      valid: innerResult.valid,
      invalid: innerResult.invalid,
    );
  }
}

class _CareerProfileEditQuery implements ProfileEditQuery {
  const _CareerProfileEditQuery();

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    return const ProfileEditSnapshotData(
      ownerUserId: 'owner-1',
      personaId: 'persona-1',
      avatarUrl: '',
      avatarAssetId: '',
      avatarVersion: 0,
      backgroundUrl: '',
      backgroundAssetId: '',
      nickname: '测试用户',
      gender: 'unspecified',
      birthDate: '',
      region: '',
      regionTagRef: '',
      userHandle: 'test_user',
      bio: '',
      occupationTagRef: '',
      interestTagRefs: <String>[],
    );
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() {
    throw UnimplementedError();
  }

  @override
  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) {
    throw UnimplementedError();
  }
}

class _CareerInterestHost extends StatefulWidget {
  const _CareerInterestHost();

  @override
  State<_CareerInterestHost> createState() => _CareerInterestHostState();
}

class _CareerInterestHostState extends State<_CareerInterestHost> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Navigator.of(context).push<bool>(
              MaterialPageRoute<bool>(
                builder: (_) => const CareerInterestPage(),
              ),
            );
          },
          child: const Text('打开职业与兴趣'),
        ),
      ),
    );
  }
}
