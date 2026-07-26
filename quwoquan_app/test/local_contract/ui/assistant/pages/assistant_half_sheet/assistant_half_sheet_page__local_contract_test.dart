/// assistantHalfSheet 半弹层 user_acceptance（B8 阶段 4a：真实 widget pump 验收）。
///
/// surface: assistantHalfSheet · owner: assistant · route: assistantPersonal
/// 本文件替代旧「证据文件路径存在性断言」伪验收。承载关系说明：
/// - 半弹层 surface 的 UI 本体由 production `AssistantHalfSheet.show(...)`
///   经真实 `showModalBottomSheet` 呼出，不再验收生产不可达的旁路；
/// 四类必测 case：
/// - load_success：真实弹出后核心结构出现（欢迎语 + 建议区标题 + 主 CTA 文案）；
/// - empty_permission_error：personalization Facet 抛 CloudException →
///   provider AsyncError → UI 展示结构化错误，不伪造本地个性化内容；
/// - primary_cta：「进入完整对话」及输入提交都真实 push 完整对话路由；
/// - trace_context：打开半弹层先上报页面上下文（reportPageContext，
///   userAction=open_assistant_entry），context snapshot 与来源一致。
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime_failure_fixtures.dart';

const _showEntryButtonKey = ValueKey<String>('uat_show_entry_button');
const _destinationStubKey = ValueKey<String>('uat_assistant_personal_stub');
const _initialQueryStubKey = ValueKey<String>('uat_assistant_initial_query');
const _suggestedActionStubKey = ValueKey<String>('uat_suggested_action_id');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  _mockPathProvider();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_assistant_half_sheet_uat_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('load_success：真实弹出半弹层出现个性化欢迎区与主 CTA', (tester) async {
    final facet = _RecordingPersonalizationFacet();
    final openContext = _openContext();
    await _pumpLauncher(tester, facet: facet, openContext: openContext);
    await _openHalfSheet(tester);

    expect(find.byType(AssistantHalfSheet), findsOneWidget);
    // 服务端个性化欢迎语与 chips 真实渲染。
    expect(find.text('服务端欢迎语（UAT）'), findsOneWidget);
    expect(find.text('服务端找资料'), findsOneWidget);
    // 「当前适合干啥」建议区与主 CTA 文案出现。
    expect(
      find.text(AssistantText.assistantHalfSheetSuggestionTitle),
      findsOneWidget,
    );
    expect(find.text('服务端动作'), findsOneWidget);
    expect(
      find.text(AssistantText.assistantHalfSheetEnterFullChat),
      findsOneWidget,
    );

    await _disposeTree(tester);
  });

  testWidgets('empty_permission_error：Facet 抛 CloudException 时展示结构化错误', (
    tester,
  ) async {
    final facet = _RecordingPersonalizationFacet(
      entryError: CloudException(
        type: CloudErrorType.forbidden,
        message: 'skill consent required',
        statusCode: AssistantErrorCode.skillConsentRequired.httpStatus,
        code: AssistantErrorCode.skillConsentRequired.code,
        userMessage: AssistantErrorCode.skillConsentRequired.defaultMessage,
        runtimeFailure: testRuntimeFailure(
          code: AssistantErrorCode.skillConsentRequired.code,
          kind: RuntimeFailureKind.permission,
        ),
      ),
    );
    final openContext = _openContext();
    await _pumpLauncher(tester, facet: facet, openContext: openContext);
    await _openHalfSheet(tester);

    // 错误走 provider 错误通道（结构化 CloudException，不吞错；Riverpod 3
    // 失败后自动重试，状态可能为携带 error 的 AsyncLoading，故断言 hasError）。
    final container = ProviderScope.containerOf(
      tester.element(find.byType(AssistantHalfSheet)),
    );
    final personalization = container.read(
      assistantHalfSheetPersonalizationProvider(openContext),
    );
    expect(personalization.hasError, isTrue);
    expect(personalization.error, isA<CloudException>());
    expect(
      (personalization.error! as CloudException).code,
      AssistantErrorCode.skillConsentRequired.code,
    );

    // 失败关闭：不得回落到本地静态欢迎语或 chips 伪造服务端成功。
    expect(
      find.text(AssistantErrorCode.skillConsentRequired.defaultMessage),
      findsOneWidget,
    );
    expect(find.text('服务端欢迎语（UAT）'), findsNothing);
    expect(find.text('服务端找资料'), findsNothing);
    // 半弹层本体不崩溃，主 CTA 仍可用。
    expect(find.byType(AssistantHalfSheet), findsOneWidget);
    expect(
      find.text(AssistantText.assistantHalfSheetEnterFullChat),
      findsOneWidget,
    );

    await _disposeTree(tester);
  });

  testWidgets('primary_cta：production 半弹层的完整对话按钮与输入提交都进入会话', (tester) async {
    final facet = _RecordingPersonalizationFacet();
    final openContext = _openContext();
    final router = await _pumpLauncher(
      tester,
      facet: facet,
      openContext: openContext,
    );
    await _openHalfSheet(tester);

    // 半弹层内主 CTA：关闭 sheet 并进入完整对话路由（断言用户可见的
    // 目的地页面真实渲染；go_router 命令式 push 不回写 URI）。
    await tester.tap(find.text(AssistantText.assistantHalfSheetEnterFullChat));
    await tester.pumpAndSettle();
    expect(find.byType(AssistantHalfSheet), findsNothing);
    expect(find.byKey(_destinationStubKey), findsOneWidget);
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      AppRoutePaths.assistantPersonal,
    );

    // 返回入口页，再验 production show() 静态入口真实呼出半弹层。
    router.go('/uat-home');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(_showEntryButtonKey));
    await tester.pumpAndSettle();
    expect(find.byType(AssistantHalfSheet), findsOneWidget);

    // 输入框提交会携带首条问题进入完整对话，目的地可消费 autoSendQuery。
    const initialQuery = '帮我整理今晚的安排';
    await tester.enterText(find.byType(TextField), initialQuery);
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(find.byKey(_destinationStubKey), findsOneWidget);
    expect(find.text(initialQuery), findsOneWidget);
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      AppRoutePaths.assistantPersonal,
    );

    await _disposeTree(tester);
  });

  testWidgets('suggested_action：服务端建议动作将携带动作标识进入完整对话', (tester) async {
    final facet = _RecordingPersonalizationFacet();
    final openContext = _openContext();
    await _pumpLauncher(tester, facet: facet, openContext: openContext);
    await _openHalfSheet(tester);

    await tester.tap(find.text('服务端动作'));
    await tester.pumpAndSettle();

    expect(find.byKey(_destinationStubKey), findsOneWidget);
    expect(find.text('服务端动作'), findsOneWidget);
    expect(find.byKey(_suggestedActionStubKey), findsOneWidget);
    expect(find.text('uat_action'), findsOneWidget);

    await _disposeTree(tester);
  });

  testWidgets('trace_context：打开半弹层先上报页面上下文且 snapshot 与来源一致', (tester) async {
    final facet = _RecordingPersonalizationFacet();
    final openContext = _openContext();
    await _pumpLauncher(tester, facet: facet, openContext: openContext);
    await _openHalfSheet(tester);

    // 埋点顺序契约：先 reportPageContext（open_assistant_entry），再取个性化。
    expect(
      facet.calls,
      containsAllInOrder(<String>[
        'reportPageContext:open_assistant_entry',
        'getEntryPersonalization',
        'getSuggestedActions',
      ]),
    );
    // 页面上下文只保留服务端可验证的最小定位与当前页读取授权。
    expect(facet.lastContextSnapshot?.pageType, 'discovery');
    expect(
      facet.lastContextSnapshot?.consentMatrix?.canReadCurrentPage,
      isTrue,
    );
    expect(facet.lastContextSnapshot?.pageObjects, isEmpty);

    await _disposeTree(tester);
  });
}

AssistantOpenContext _openContext() {
  return const AssistantOpenContext(
    source: AssistantSource.discovery,
    visitTarget: VisitTarget.page('discovery'),
    experienceLevel: ExperienceLevel.returning,
  );
}

/// pump 半弹层宿主：GoRouter 提供 launcher 页与完整对话目的地路由。
Future<GoRouter> _pumpLauncher(
  WidgetTester tester, {
  required _RecordingPersonalizationFacet facet,
  required AssistantOpenContext openContext,
}) async {
  final router = GoRouter(
    initialLocation: '/uat-home',
    routes: <RouteBase>[
      GoRoute(
        path: '/uat-home',
        builder: (_, _) => _SheetLauncherPage(openContext: openContext),
      ),
      GoRoute(
        path: AppRoutePaths.assistantPersonal,
        builder: (_, state) {
          final extra = state.extra is AssistantOpenContext
              ? state.extra as AssistantOpenContext
              : null;
          final initialQuery =
              extra?.hints['autoSendQuery']?.toString().trim() ?? '';
          final suggestedActionID =
              extra?.hints['suggestedActionId']?.toString().trim() ?? '';
          return Scaffold(
            body: Column(
              children: <Widget>[
                const SizedBox(key: _destinationStubKey),
                Text(initialQuery, key: _initialQueryStubKey),
                Text(suggestedActionID, key: _suggestedActionStubKey),
              ],
            ),
          );
        },
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        assistantPersonalizationFacetProvider.overrideWithValue(facet),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pump();
  return router;
}

/// 通过 production 静态入口呼出真实 modal bottom sheet。
Future<void> _openHalfSheet(WidgetTester tester) async {
  await tester.tap(find.byKey(_showEntryButtonKey));
  await tester.pumpAndSettle();
  expect(find.byType(AssistantHalfSheet), findsOneWidget);
}

Future<void> _disposeTree(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 50));
}

void _mockPathProvider() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final directory = Directory.systemTemp.createTempSync(
    'qwq_assistant_half_sheet_uat_fs_',
  );
  tearDownAll(() {
    if (directory.existsSync()) {
      directory.deleteSync(recursive: true);
    }
  });
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return directory.path;
          default:
            return null;
        }
      });
}

/// 半弹层宿主页：只暴露 production `AssistantHalfSheet.show` 入口。
class _SheetLauncherPage extends StatelessWidget {
  const _SheetLauncherPage({required this.openContext});

  final AssistantOpenContext openContext;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            ElevatedButton(
              key: _showEntryButtonKey,
              onPressed: () => AssistantHalfSheet.show(context, openContext),
              child: const Text('show-entry'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Recording 个性化 Facet：记录调用顺序与 context snapshot；可配置抛错。
class _RecordingPersonalizationFacet implements AssistantPersonalizationFacet {
  _RecordingPersonalizationFacet({this.entryError});

  final Object? entryError;
  final List<String> calls = <String>[];
  AssistantContextSnapshot? lastContextSnapshot;

  @override
  Future<PageContextAck> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    calls.add('reportPageContext:$userAction');
    lastContextSnapshot = assistantContextSnapshotFromOpenContext(
      context,
      userAction: userAction,
    );
    return const PageContextAck(accepted: true, contextKey: 'ctx_uat');
  }

  @override
  Future<AssistantEntryPersonalizationView> getEntryPersonalization({
    required AssistantOpenContext context,
  }) async {
    calls.add('getEntryPersonalization');
    final error = entryError;
    if (error != null) {
      throw error;
    }
    return const AssistantEntryPersonalizationView(
      welcomeMessage: '服务端欢迎语（UAT）',
      suggestionLines: <String>['服务端建议'],
      chips: <AssistantEntryPersonalizationChipView>[
        AssistantEntryPersonalizationChipView(
          chipId: 'uat_find',
          label: '服务端找资料',
          actionType: 'command',
          value: 'find',
        ),
      ],
      personalized: true,
    );
  }

  @override
  Future<SuggestedActionListView> getSuggestedActions({
    required AssistantOpenContext context,
  }) async {
    calls.add('getSuggestedActions');
    return const SuggestedActionListView(
      items: <SuggestedAction>[
        SuggestedAction(
          actionId: 'uat_action',
          type: 'command',
          label: '服务端动作',
        ),
      ],
    );
  }
}
