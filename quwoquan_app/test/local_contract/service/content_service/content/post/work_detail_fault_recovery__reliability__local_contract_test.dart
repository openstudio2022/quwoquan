/// 作品详情直达入口的断连降级与恢复契约（typed fault 注入 → 显式错误态 → 恢复重试成功）。
///
/// 与既有 flaky 单次失败用例互补：本测试消费测试树共享故障闭集
/// （disconnect），验证故障持续期间错误态保持、deactivate 后同装配
/// 经恢复动作取回真实详情。
///
/// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentPostDetailReader;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/work_browser_entry_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/fault/typed_fault_injection.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

const _postId = 'fault-recovery-article';

InMemoryContentPostStore _suiteStore() {
  final post = contentPostViewDataBuilder(
    postId: _postId,
    contentType: 'article',
    title: '可靠性样本文章',
  );
  return InMemoryContentPostStore(
    posts: <ContentPostViewData>[post],
    details: <String, ContentPostDetailPayload>{
      _postId: contentPostDetailPayloadBuilder(
        post: post,
        articleMarkdown: '# 可靠性样本文章\n\n正文。',
      ),
    },
  );
}

/// 组合共享 TypedFaultInjector 的详情读 double：故障态由测试切换。
final class _FaultInjectingDetailReader extends Fake
    implements ContentPostDetailReader {
  _FaultInjectingDetailReader(this._delegate, this.injector);

  final InMemoryContentPostDetailReader _delegate;
  final TypedFaultInjector injector;

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    return injector.guard(
      () => _delegate.getPost(
        postId: postId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      ),
    );
  }
}

void main() {
  testWidgets('断连故障下详情入口保持显式错误态，恢复后重试取回真实详情', (tester) async {
    final injector = TypedFaultInjector();
    final store = _suiteStore();
    final reader = _FaultInjectingDetailReader(
      InMemoryContentPostDetailReader(store),
      injector,
    );

    injector.activate(TypedFaultProfile.disconnect);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...mockContentFacetOverrides(
            store: store,
            workBrowserDetailReader: reader,
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildAlphaContentRuntimeConfigDefaults(),
          ),
        ],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const WorkBrowserEntryPage(
              workId: _postId,
              source: 'fault-recovery-reliability-test',
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final errorFinder = find.byKey(const ValueKey('work-browser-entry-error'));
    expect(errorFinder, findsOneWidget, reason: '断连必须呈现显式错误态');
    final errorState = tester.widget<AppPageErrorState>(errorFinder);
    expect(
      errorState.semantic.primaryAction?.type,
      UiErrorActionType.retry,
      reason: '可恢复故障必须提供重试恢复动作',
    );

    // 故障持续期间重试仍保持错误态，不得伪成功。
    await errorState.onRecovery!(
      const UiErrorAction(type: UiErrorActionType.retry, label: '重试'),
    );
    await tester.pumpAndSettle();
    expect(errorFinder, findsOneWidget, reason: '故障未恢复时重试不得伪成功');

    injector.deactivate();
    final recoveredState = tester.widget<AppPageErrorState>(errorFinder);
    final outcome = await recoveredState.onRecovery!(
      const UiErrorAction(type: UiErrorActionType.retry, label: '重试'),
    );
    expect(outcome, UiRecoveryOutcome.recovered);
    await tester.pumpAndSettle();
    expect(errorFinder, findsNothing, reason: '恢复后同装配重试必须取回真实详情');
  });
}
