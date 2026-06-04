import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_maintenance_page.dart';

void main() {
  testWidgets('主页维护页加载失败时展示统一页态', (tester) async {
    await tester.pumpWidget(
      _buildApp(repository: _LoadFailingHomepageRepository()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(UITextConstants.retry), findsOneWidget);
  });

  testWidgets('主页维护页提交失败时展示统一区块错误卡', (tester) async {
    await tester.pumpWidget(
      _buildApp(repository: _SubmitFailingHomepageRepository()),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(CupertinoTextField).first, '新的主页名称');
    await tester.tap(find.text('保存主页信息'));
    await tester.pumpAndSettle();

    expect(find.byType(AppSectionErrorCard), findsOneWidget);
    expect(find.text('提交未完成'), findsOneWidget);
  });
}

Widget _buildApp({required HomepageRepository repository}) {
  return ProviderScope(
    overrides: [
      homepageRepositoryProvider.overrideWithValue(repository),
    ],
    child: const MaterialApp(
      home: HomepageMaintenancePage(homepageId: 'homepage_sight_west_lake'),
    ),
  );
}

class _LoadFailingHomepageRepository extends MockHomepageRepository {
  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    throw StateError('load failed');
  }
}

class _SubmitFailingHomepageRepository extends MockHomepageRepository {
  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final detail = await super.getHomepageDetail(homepageId);
    return detail.copyWith(claimStatus: 'claimed');
  }

  @override
  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  }) async {
    throw StateError('submit failed');
  }
}
