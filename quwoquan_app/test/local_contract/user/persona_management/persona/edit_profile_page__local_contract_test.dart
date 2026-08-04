// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-003
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/user/pages/edit_profile_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ProfileEditSnapshotData _snapshot() {
  return const ProfileEditSnapshotData(
    ownerUserId: 'owner_edit',
    personaId: 'ps_edit',
    avatarUrl: '',
    avatarAssetId: '',
    avatarVersion: 0,
    backgroundUrl: '',
    backgroundAssetId: '',
    nickname: '旅行者小林',
    gender: 'female',
    birthDate: '1998-06-01',
    region: '浙江杭州',
    regionTagRef: 'tag:region/zhejiang/hangzhou',
    userHandle: 'traveler_lin',
    bio: '记录每一次出发',
    occupationTagRef: '',
    interestTagRefs: <String>[],
  );
}

class _StubProfileEditQuery implements ProfileEditQuery {
  _StubProfileEditQuery({this.error});

  final Object? error;
  int snapshotCalls = 0;

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    snapshotCalls++;
    final failure = error;
    if (failure != null) throw failure;
    return _snapshot();
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() async {
    throw UnimplementedError('qr card is not part of this contract');
  }

  @override
  Future<ProfileQrResolveWire> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    throw UnimplementedError('qr resolve is not part of this contract');
  }
}

class _StubProposalReader implements ProfileUpdateProposalQueryReader {
  @override
  Future<ProfileUpdateProposalView> get(
    ProfileUpdateProposalQuery query,
  ) async {
    throw UnimplementedError('single proposal read is not used by the page');
  }

  @override
  Future<ProfileUpdateProposalSlice> list(
    ProfileUpdateProposalListQuery query,
  ) async {
    return const ProfileUpdateProposalSlice(
      items: <ProfileUpdateProposalView>[],
    );
  }
}

Widget _host({
  required ProfileEditQuery editQuery,
  required ProfileUpdateProposalQueryReader proposals,
}) {
  return ProviderScope(
    overrides: [
      profileEditQueryProvider.overrideWith((ref, surface) => editQuery),
      profileEditProposalQueryReaderProvider.overrideWithValue(proposals),
    ],
    child: const CupertinoApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: EditProfilePage(),
    ),
  );
}

void main() {
  testWidgets('编辑资料页从 ProfileEditQuery typed 快照渲染字段', (tester) async {
    final editQuery = _StubProfileEditQuery();
    await tester.pumpWidget(
      _host(editQuery: editQuery, proposals: _StubProposalReader()),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(editQuery.snapshotCalls, 1);
    // 昵称与地区必须来自 typed 快照，不得使用本地拼装值。
    expect(find.text('旅行者小林'), findsWidgets);
    expect(find.text('浙江杭州'), findsOneWidget);
  });

  testWidgets('快照加载失败展示统一页面错误态（不落空白页）', (tester) async {
    final editQuery = _StubProfileEditQuery(error: StateError('snapshot down'));
    await tester.pumpWidget(
      _host(editQuery: editQuery, proposals: _StubProposalReader()),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(SearchText.reload), findsWidgets);
  });
}
