// creator_chip 采集通道的生产写入点合同：发布确认页打开打标 chip 页，
// 选中语义标签写入 PublishSettings.tagRefs 并进入发布 payload；
// 单轴加载失败只降级该分组；选择数量受上限约束。
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-003.t4
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#req-001

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_location_coordinator.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_publish_confirm_sheet.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/publish_tag_chip_picker_page.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        TagChildView,
        TagLifecycleStatus,
        TagResolveView,
        TagValidationResultView;

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/platform/location/fake_location_gateway.dart';
import '../../../../../support/service/integration_service/external_integration/location/fake_location_readers.dart';

TagChildView _chip(String parent, String label) => TagChildView(
  tagRef: '$parent/$label',
  label: label,
  parentTagRef: parent,
  depth: parent.split('/').length + 1,
  hasChildren: false,
  releaseId: 'taxonomy-test-release',
  lifecycleStatus: TagLifecycleStatus.active,
);

final class _ChipCatalogDouble implements TagCatalogQuery {
  _ChipCatalogDouble(this.childrenByParent, {this.failingParents = const {}});

  final Map<String, List<TagChildView>> childrenByParent;
  final Set<String> failingParents;

  @override
  Future<List<TagChildView>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    if (failingParents.contains(parentTagRef)) {
      throw StateError('TAG.SYSTEM.unavailable: $parentTagRef');
    }
    return childrenByParent[parentTagRef] ?? const <TagChildView>[];
  }

  @override
  Future<TagResolveView> resolveTag(String tagRef) =>
      throw UnimplementedError();

  @override
  Future<TagValidationResultView> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  }) => throw UnimplementedError();
}

Widget _buildApp({
  required TagCatalogQuery catalog,
  required ValueChanged<PublishSettings> onConfirm,
}) {
  return ProviderScope(
    overrides: <Override>[
      ...sealedCloudBoundaryOverrides(),
      tagCatalogQueryProvider.overrideWithValue(catalog),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => CupertinoApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CupertinoPageScaffold(
          child: Builder(
            builder: (context) => Center(
              child: CupertinoButton(
                child: const Text('打开发布确认'),
                onPressed: () async {
                  final result = await Navigator.of(context)
                      .push<PublishSettings>(
                        CupertinoPageRoute<PublishSettings>(
                          builder: (_) => CreatePublishConfirmSheet(
                            initialSettings: const PublishSettings(),
                            locationCoordinator: CreateLocationCoordinator(
                              nearbyReader: FakeLocationQueryAdapter(),
                              searchReader: FakeLocationQueryAdapter(),
                              locationGateway: FakeLocationGateway(),
                            ),
                            joinedCircles: const <CreateCircleOption>[],
                            recommendedCircles: const <CreateCircleOption>[],
                          ),
                        ),
                      );
                  if (result != null) {
                    onConfirm(result);
                  }
                },
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

Future<void> _openPicker(WidgetTester tester) async {
  await tester.tap(find.text('打开发布确认'));
  await tester.pumpAndSettle();
  await tester.tap(find.text(CreationText.contentTagsLabel));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('选中 chip 后 tagRefs 写入发布设置并进入 payload（creator_chip 通道）', (
    tester,
  ) async {
    PublishSettings? confirmed;
    final catalog = _ChipCatalogDouble(<String, List<TagChildView>>{
      'Topic/旅行/同行人': <TagChildView>[
        _chip('Topic/旅行/同行人', '情侣同行'),
        _chip('Topic/旅行/同行人', '朋友结伴'),
      ],
      'Topic/旅行/预算档次': <TagChildView>[_chip('Topic/旅行/预算档次', '穷游')],
    });

    await tester.pumpWidget(
      _buildApp(catalog: catalog, onConfirm: (s) => confirmed = s),
    );
    await tester.pumpAndSettle();
    await _openPicker(tester);

    expect(find.text(CreationText.contentTagsPickerTitle), findsOneWidget);
    await tester.tap(find.text('情侣同行'));
    await tester.pump();
    await tester.tap(find.text('穷游'));
    await tester.pump();
    await tester.tap(
      find.byKey(const ValueKey<String>('publish-tag-chip-picker-confirm')),
    );
    await tester.pumpAndSettle();

    // 回到发布确认页，行 value 显示已选标签尾段。
    expect(find.textContaining('情侣同行'), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(
      confirmed!.tagRefs.toSet(),
      <String>{'Topic/旅行/同行人/情侣同行', 'Topic/旅行/预算档次/穷游'},
    );
    expect(
      (confirmed!.toPayloadFields()['tagRefs'] as List).toSet(),
      <String>{'Topic/旅行/同行人/情侣同行', 'Topic/旅行/预算档次/穷游'},
      reason: 'chip 声明的语义标签必须进入发布 payload，供推荐召回与交集消费',
    );
  });

  testWidgets('chip 选择数量受上限约束，超出后不再追加', (tester) async {
    PublishSettings? confirmed;
    final catalog = _ChipCatalogDouble(<String, List<TagChildView>>{
      'Topic/旅行/同行人': <TagChildView>[
        for (var i = 1; i <= kCreatorChipSelectionLimit + 1; i++)
          _chip('Topic/旅行/同行人', '候选$i'),
      ],
    });

    await tester.pumpWidget(
      _buildApp(catalog: catalog, onConfirm: (s) => confirmed = s),
    );
    await tester.pumpAndSettle();
    await _openPicker(tester);

    for (var i = 1; i <= kCreatorChipSelectionLimit + 1; i++) {
      await tester.tap(find.text('候选$i'));
      await tester.pump();
    }
    await tester.tap(
      find.byKey(const ValueKey<String>('publish-tag-chip-picker-confirm')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.tagRefs.length, kCreatorChipSelectionLimit);
    expect(
      confirmed!.tagRefs.contains(
        'Topic/旅行/同行人/候选${kCreatorChipSelectionLimit + 1}',
      ),
      isFalse,
      reason: '超出上限的点击不得追加',
    );
  });

  testWidgets('单轴加载失败只降级该分组，其余轴可选且发布不受阻', (tester) async {
    PublishSettings? confirmed;
    final catalog = _ChipCatalogDouble(
      <String, List<TagChildView>>{
        'Topic/旅行/预算档次': <TagChildView>[_chip('Topic/旅行/预算档次', '穷游')],
      },
      failingParents: <String>{'Topic/旅行/同行人'},
    );

    await tester.pumpWidget(
      _buildApp(catalog: catalog, onConfirm: (s) => confirmed = s),
    );
    await tester.pumpAndSettle();
    await _openPicker(tester);

    expect(
      find.text(CreationText.contentTagsAxisLoadFailed),
      findsOneWidget,
      reason: '失败轴以固定文案降级，不得整页失败',
    );
    await tester.tap(find.text('穷游'));
    await tester.pump();
    await tester.tap(
      find.byKey(const ValueKey<String>('publish-tag-chip-picker-confirm')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.tagRefs, <String>['Topic/旅行/预算档次/穷游']);
  });
}
