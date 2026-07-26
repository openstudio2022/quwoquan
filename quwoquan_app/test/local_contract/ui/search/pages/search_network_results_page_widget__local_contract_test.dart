// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/search-intersection-consumption/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/ui/search/models/search_result_tab_spec.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

import '../../../../support/recording_app_telemetry_recorder.dart';

/// 小趣搜确定性替身：成功返回带 queryEcho/summary 的合法结果。
class _FakeXiaoquSearchFacet implements AssistantXiaoquSearchFacet {
  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    return AssistantSearchResultView(
      queryEcho: query.trim(),
      summary: '已为“${query.trim()}”整理公开线索摘要（test fixture）。',
      searchIntensity: searchIntensity,
      citations: const <AssistantSearchCitationView>[],
    );
  }
}

/// 小趣搜失败替身：B8-3b 后 Remote 失败一律抛结构化 CloudException。
class _ThrowingXiaoquSearchFacet implements AssistantXiaoquSearchFacet {
  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    throw CloudErrorMapper.fromException(
      StateError('xiaoqu search unavailable (test)'),
      requestPath: '/assistant/search/xiaoqu',
    );
  }
}

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
    prefilledQuery: '影',
    initialNetworkTabId: 'all',
  ),
}) {
  return ProviderScope(
    overrides: [
      appDataSourceModeProvider.overrideWith(_MockModeNotifier.new),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      searchFeedbackCommandWriterProvider.overrideWithValue(
        AlphaSearchFeedbackWriter(),
      ),
    ],
    child: MaterialApp(
      home: SearchNetworkResultsPage(launchContext: launchContext),
    ),
  );
}

Widget _buildAppWithSearchRepository({
  required SearchLaunchContext launchContext,
  required SearchRepository repository,
  AssistantXiaoquSearchFacet? xiaoquFacet,
  ContentPostDetailReader? postDetailReader,
  SearchFeedbackCommandWriter? feedbackWriter,
  RecordingAppTelemetryRecorder? telemetryRecorder,
}) {
  return ProviderScope(
    overrides: [
      appDataSourceModeProvider.overrideWith(_MockModeNotifier.new),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      searchRepositoryProvider.overrideWithValue(repository),
      searchFeedbackCommandWriterProvider.overrideWithValue(
        feedbackWriter ?? AlphaSearchFeedbackWriter(),
      ),
      if (telemetryRecorder != null)
        appTelemetryReporterProvider.overrideWithValue(telemetryRecorder),
      if (postDetailReader != null)
        globalSearchContentPostDetailReaderProvider.overrideWithValue(
          postDetailReader,
        ),
      if (xiaoquFacet != null)
        assistantXiaoquSearchFacetProvider.overrideWithValue(xiaoquFacet),
    ],
    child: MaterialApp(
      home: SearchNetworkResultsPage(launchContext: launchContext),
    ),
  );
}

final class _MockModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;
}

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  Future<void> pumpSearchResultsPage(WidgetTester tester, Widget widget) async {
    tester.view.physicalSize = const Size(1080, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(widget);
  }

  testWidgets('网络结果页固定 Tab 并默认进入全部', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '影',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    expect(find.text('小趣'), findsOneWidget);
    expect(find.text('全部'), findsWidgets);
    expect(
      tester.getTopLeft(find.text('小趣')).dx,
      lessThan(tester.getTopLeft(find.text('全部').first).dx),
    );
    expect(find.text('交集'), findsOneWidget);
    expect(find.text('图片'), findsOneWidget);
    expect(find.text('视频'), findsOneWidget);
    expect(find.text('长文'), findsOneWidget);
    expect(find.textContaining('已加入圈子'), findsNothing);
    expect(find.textContaining('聊天记录'), findsNothing);
    expect(find.textContaining('全站结果'), findsNothing);
    expect(find.text('相关搜索'), findsWidgets);
    expect(find.text('影 攻略'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
    expect(find.text('相关用户'), findsOneWidget);
    expect(find.text('林同学'), findsOneWidget);
    expect(find.text('推荐'), findsNothing);
    expect(find.text('遇见'), findsNothing);
    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(tabBar.tabs, <String>['小趣', '全部', '交集', '图片', '视频', '长文']);
    expect(find.textContaining('小趣正在整理'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('search_network_submit_button')),
      findsOneWidget,
    );
  });

  testWidgets('搜索对象漏斗上报提交、结果、筛选与停留且不携带原始查询', (tester) async {
    final telemetry = RecordingAppTelemetryRecorder();
    final feedback = AlphaSearchFeedbackWriter();
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '摄影隐私样例',
          initialNetworkTabId: 'all',
        ),
        repository: _TelemetrySearchRepository(),
        feedbackWriter: feedback,
        telemetryRecorder: telemetry,
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => telemetry.recorded.any(
        (event) => event.eventType == 'search_result_impression',
      ),
    );

    final submit = telemetry.recorded.singleWhere(
      (event) => event.eventType == 'search_query_submit',
    );
    final impression = telemetry.recorded.singleWhere(
      (event) => event.eventType == 'search_result_impression',
    );
    expect(submit.extensions['requestId'], 'search-telemetry-1');
    expect(submit.extensions['surfaceId'], 'globalSearchNetworkResults');
    expect(submit.occurredAt, isNotNull);
    expect(impression.extensions['resultCount'], 1);
    for (final event in telemetry.recorded.where(
      (item) => item.eventType.startsWith('search_'),
    )) {
      expect(event.extensions, isNot(contains('query')));
      expect(event.extensions, isNot(contains('objectId')));
      expect(event.extensions, isNot(contains('userId')));
    }

    await tester.tap(find.text('图片'));
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () =>
          telemetry.recorded
              .where((event) => event.eventType == 'search_result_impression')
              .length ==
          2,
    );
    expect(
      telemetry.recorded
          .singleWhere((event) => event.eventType == 'search_refine')
          .extensions['action'],
      'tab:image',
    );
    expect(
      feedback.recorded.any((event) => event.eventType == 'refine'),
      isTrue,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    final dwellEvents = telemetry.recorded.where(
      (event) => event.eventType == 'search_result_dwell',
    );
    expect(dwellEvents, isNotEmpty);
    expect(dwellEvents.last.extensions['resultCount'], 1);
  });

  testWidgets('零结果只上报 zero_result 不得把空态停留计为有效行动', (tester) async {
    final telemetry = RecordingAppTelemetryRecorder();
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '没有命中的商业词',
          initialNetworkTabId: 'all',
        ),
        repository: _TelemetrySearchRepository(empty: true),
        telemetryRecorder: telemetry,
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => telemetry.recorded.any(
        (event) => event.eventType == 'search_zero_result',
      ),
    );

    expect(
      telemetry.recorded.where(
        (event) => event.eventType == 'search_result_impression',
      ),
      isEmpty,
    );
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 4));
    expect(
      telemetry.recorded.where(
        (event) => event.eventType == 'search_result_dwell',
      ),
      isEmpty,
    );
  });

  testWidgets('空结果回显查询词并允许重新编辑', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '不存在的词条',
          initialNetworkTabId: 'all',
        ),
        repository: _EmptyNetworkSearchRepository(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('没有找到“不存在的词条”的结果'), findsOneWidget);
    expect(find.text('试试缩短关键词、检查错别字，或搜索更宽泛的对象。'), findsOneWidget);
    expect(find.text('调整关键词'), findsOneWidget);
    expect(find.text(UITextConstants.searchRelatedTitle), findsOneWidget);
    expect(find.text('摄影'), findsOneWidget);

    await tester.tap(find.text('调整关键词'));
    await tester.pump();

    final field = tester.widget<EditableText>(find.byType(EditableText));
    expect(field.controller.text, isEmpty);
    expect(field.focusNode.hasFocus, isTrue);
  });

  testWidgets('正式结果页每个 generation 只调用一次 canonical search', (tester) async {
    final repository = _RecordingCanonicalSearchRepository();
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '影',
          initialNetworkTabId: 'all',
        ),
        repository: repository,
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    expect(repository.requests, hasLength(1));
    expect(repository.requests.single.objectTypes, <SearchObjectType>{
      SearchObjectType.contentPost,
      SearchObjectType.userProfile,
      SearchObjectType.entityHomepage,
      SearchObjectType.locationPlace,
    });
  });

  testWidgets('结果页搜索按钮可按新关键词重新加载', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    await tester.enterText(
      find.byKey(const ValueKey<String>('search_network_field')),
      '西湖',
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('search_network_submit_button')),
    );
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖').evaluate().isNotEmpty,
    );

    expect(find.text('实体主页'), findsOneWidget);
    expect(find.text('西湖摄影讨论'), findsNothing);
  });

  testWidgets('交集 tab 按云侧 connectionState 分组并只读 primaryText', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '影',
          initialNetworkTabId: 'all',
        ),
        repository: _IntersectionContractSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.text('交集'));
    await _pumpUntil(
      tester,
      condition: () => find.text('已形成的连接').evaluate().isNotEmpty,
    );

    // connectionState=connected 的命中进入「已形成的连接」。
    expect(find.text('已形成的连接'), findsOneWidget);
    expect(find.text('你点赞过的海边日落'), findsWidgets);

    // intersection_lead / unconnected 的命中进入「发现更多交集」。
    expect(find.text('发现更多交集'), findsOneWidget);
    expect(find.text('环岛路骑行机位合集'), findsWidgets);
    expect(find.text('城市天际线拍摄攻略'), findsWidgets);

    // 交集句严格只读云侧 intersectionReason.primaryText。
    expect(find.text('你关注的小林也在拍这里'), findsWidgets);

    // 无 primaryText 的命中不得出现端侧拼装/旧字段回退/违禁词。
    expect(find.textContaining('共同兴趣'), findsNothing);
    expect(find.textContaining('感兴趣圈子'), findsNothing);
    expect(find.textContaining('交集发现流'), findsNothing);
    expect(find.textContaining('好友'), findsNothing);
    expect(find.textContaining('因为你'), findsNothing);
  });

  testWidgets('全部 tab 顶卡只来自云侧 entity.homepage 单源', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('实体主页').evaluate().isNotEmpty,
    );

    // 顶卡走 entity.homepage（badge=实体主页 + 关注/内容计数来自 payload）。
    expect(find.text('实体主页'), findsOneWidget);
    expect(find.text('西湖'), findsWidgets);
    // 不再出现三方 POI 旁路（integration.location_poi 已下线于结果页）。
    expect(find.text('浙江省杭州市西湖区'), findsNothing);
  });

  testWidgets('交集 tab 已连接地点来自云侧 location.place', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.text('交集'));
    await _pumpUntil(
      tester,
      condition: () => find.text('已形成的连接').evaluate().isNotEmpty,
    );

    // connectionState=connected 的 location.place 进入「已形成的连接」。
    expect(find.text('已形成的连接'), findsOneWidget);
    expect(find.textContaining('西湖旁断桥小巷'), findsWidgets);
  });

  testWidgets('旧主页 tab 深链归一到全部', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildApp(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'homepages',
        ),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(tabBar.tabs[tabBar.activeIndex], '全部');
  });

  testWidgets('全部 tab 只汇总实体顶部、媒体文章和相关搜索', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    expect(find.text('全部'), findsWidgets);
    expect(find.textContaining('聊天记录'), findsNothing);
    expect(find.text('光影摄影社主群'), findsNothing);
    expect(find.text('相关搜索'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
    expect(find.textContaining('全站结果'), findsNothing);
  });

  testWidgets('旧消息 tab 深链归一到全部但不展示聊天结果', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'messages',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖').evaluate().isNotEmpty,
    );

    expect(find.text('全部'), findsWidgets);
    expect(find.text('实体主页'), findsOneWidget);
    expect(find.text('西湖摄影讨论'), findsNothing);
  });

  testWidgets('小趣 tab 可作为初始 tab 打开', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '露营',
          initialNetworkTabId: 'xiaoqu',
        ),
        repository: _FakeNetworkSearchRepository(),
        xiaoquFacet: _FakeXiaoquSearchFacet(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('小趣'), findsWidgets);
    expect(find.textContaining('正在为你整理'), findsWidgets);
    expect(find.textContaining('已为“露营”整理公开线索摘要'), findsOneWidget);
  });

  testWidgets('小趣搜失败走结构化错误态而非假结果（B8-3b）', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '露营',
          initialNetworkTabId: 'xiaoqu',
        ),
        repository: _FakeNetworkSearchRepository(),
        xiaoquFacet: _ThrowingXiaoquSearchFacet(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    // 不再本地合成"假搜索摘要当成功"；页面进入既有结构化错误态。
    expect(find.text(UITextConstants.searchUnavailableTitle), findsOneWidget);
    expect(find.textContaining('已为“露营”整理公开线索摘要'), findsNothing);
  });

  testWidgets('不存在的 locations tab 归一到综合避免空 tab 漂移', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'locations',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(tabBar.tabs[tabBar.activeIndex], '全部');
  });

  testWidgets('degrade signal 不压过媒体结果', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'all',
        ),
        repository: _DegradedNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.searchPartialGroupFailed), findsOneWidget);
    expect(find.text('街头摄影'), findsWidgets);
  });

  testWidgets('degrade signal 在无结果时展示降级横幅', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '空结果词',
          initialNetworkTabId: 'all',
        ),
        repository: _EmptyDegradedNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.searchPartialGroupFailed), findsOneWidget);
  });

  testWidgets('失效内容留在搜索页并上报 typed degrade 反馈', (tester) async {
    final feedbackWriter = AlphaSearchFeedbackWriter();
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '过期内容',
          initialNetworkTabId: 'all',
        ),
        repository: _UnavailableResultSearchRepository(),
        postDetailReader: const _UnavailableContentPostDetailReader(
          ContentErrorCode.contentDeleted,
        ),
        feedbackWriter: feedbackWriter,
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find
          .text(_UnavailableResultSearchRepository.resultTitle)
          .evaluate()
          .isNotEmpty,
    );

    await tester.tap(
      find.text(_UnavailableResultSearchRepository.resultTitle).first,
    );
    await _pumpUntil(
      tester,
      condition: () => find
          .text(UITextConstants.searchResultUnavailableTitle)
          .evaluate()
          .isNotEmpty,
    );

    expect(
      find.text(ContentErrorMessages.zh[ContentErrorCode.contentDeleted]!),
      findsOneWidget,
    );
    expect(
      find.text(_UnavailableResultSearchRepository.resultTitle),
      findsNothing,
    );
    expect(
      feedbackWriter.recorded.where((event) => event.eventType == 'click'),
      hasLength(1),
    );
    final degrade = feedbackWriter.recorded.singleWhere(
      (event) => event.eventType == 'degrade',
    );
    expect(
      degrade.searchRequestId,
      _UnavailableResultSearchRepository.requestId,
    );
    expect(degrade.objectId, _UnavailableResultSearchRepository.postId);
    expect(degrade.target, 'posts');
  });

  testWidgets('内容类型筛选可驱动网络结果页加载指定内容结果', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: 'UI',
          initialNetworkTabId: 'humanity',
          searchObjectSelection: SearchObjectSelection(
            contentTypes: <SearchContentTypeFilter>{
              SearchContentTypeFilter.article,
            },
          ),
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('全部'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
  });

  final categoryScenarios =
      <
        ({
          String tabId,
          SearchContentTypeFilter contentType,
          String visibleTitle,
          List<String> hiddenTitles,
        })
      >[
        (
          tabId: SearchResultTabIds.image,
          contentType: SearchContentTypeFilter.image,
          visibleTitle: '图片结果',
          hiddenTitles: <String>['视频结果', '长文结果'],
        ),
        (
          tabId: SearchResultTabIds.video,
          contentType: SearchContentTypeFilter.video,
          visibleTitle: '视频结果',
          hiddenTitles: <String>['图片结果', '长文结果'],
        ),
        (
          tabId: SearchResultTabIds.article,
          contentType: SearchContentTypeFilter.article,
          visibleTitle: '长文结果',
          hiddenTitles: <String>['图片结果', '视频结果'],
        ),
      ];
  for (final scenario in categoryScenarios) {
    testWidgets('${scenario.visibleTitle} Tab 只请求并展示对应内容类型', (tester) async {
      final repository = _CategorySearchRepository();
      await pumpSearchResultsPage(
        tester,
        _buildAppWithSearchRepository(
          launchContext: SearchLaunchContext(
            entrySurfaceId: '/search',
            prefilledQuery: '分类',
            initialNetworkTabId: scenario.tabId,
          ),
          repository: repository,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(scenario.visibleTitle), findsWidgets);
      for (final hiddenTitle in scenario.hiddenTitles) {
        expect(find.text(hiddenTitle), findsNothing);
      }
      expect(repository.requestedContentTypes, contains(scenario.contentType));
    });
  }
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required bool Function() condition,
  Duration step = const Duration(milliseconds: 50),
  int maxTicks = 80,
}) async {
  for (var i = 0; i < maxTicks; i++) {
    await tester.pump(step);
    if (condition()) {
      return;
    }
  }
  throw TestFailure('Timed out while waiting for condition.');
}

/// 类别 Tab 契约 fake：按 SearchRequest.contentTypes 返回对应内容类型。
class _CategorySearchRepository implements SearchRepository {
  final Set<SearchContentTypeFilter> requestedContentTypes =
      <SearchContentTypeFilter>{};

  static const List<(PostSearchItemView, SearchContentTypeFilter)> _items =
      <(PostSearchItemView, SearchContentTypeFilter)>[
        (
          PostSearchItemView(
            postId: 'post_image',
            contentType: 'image',
            contentIdentity: 'work',
            title: '图片结果',
            authorDisplayName: '图片作者',
          ),
          SearchContentTypeFilter.image,
        ),
        (
          PostSearchItemView(
            postId: 'post_video',
            contentType: 'video',
            contentIdentity: 'work',
            title: '视频结果',
            authorDisplayName: '视频作者',
          ),
          SearchContentTypeFilter.video,
        ),
        (
          PostSearchItemView(
            postId: 'post_article',
            contentType: 'article',
            contentIdentity: 'article',
            title: '长文结果',
            authorDisplayName: '长文作者',
          ),
          SearchContentTypeFilter.article,
        ),
      ];

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (!normalized.objectTypes.contains(SearchObjectType.contentPost)) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    requestedContentTypes.addAll(normalized.contentTypes);
    final items = _items
        .where(
          (entry) =>
              normalized.contentTypes.isEmpty ||
              normalized.contentTypes.contains(entry.$2),
        )
        .map((entry) => entry.$1)
        .toList(growable: false);
    return SearchResponse(
      request: normalized,
      sections: <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: items
              .map(
                (item) => SearchHit(
                  objectType: SearchObjectType.contentPost,
                  objectId: item.postId,
                  title: item.title ?? item.postId,
                  resolvedFrom: SearchResolvedFrom.remote,
                  payload: SearchHitPayloadContentPost(item),
                ),
              )
              .toList(growable: false),
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      ],
    );
  }
}

final class _UnavailableContentPostDetailReader
    implements ContentPostDetailReader {
  const _UnavailableContentPostDetailReader(this.errorCode);

  final ContentErrorCode errorCode;

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    throw CloudErrorMapper.fromStatusCode(
      errorCode.httpStatus,
      body:
          '{"code":"${errorCode.code}",'
          '"userMessage":"${ContentErrorMessages.zh[errorCode]}"}',
      requestPath: ContentApiMetadata.getPostPath(postId: postId),
    );
  }
}

final class _UnavailableResultSearchRepository implements SearchRepository {
  static const String requestId = 'search-request-stale-result';
  static const String postId = 'post-stale-result';
  static const String resultTitle = '已被删除的摄影作品';

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    const item = PostSearchItemView(
      postId: postId,
      contentType: 'image',
      contentIdentity: 'work',
      title: resultTitle,
      authorDisplayName: '失效结果作者',
    );
    return SearchResponse(
      request: normalized,
      sections: const <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: <SearchObjectType>[SearchObjectType.contentPost],
          hits: <SearchHit>[
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: postId,
              title: resultTitle,
              resolvedFrom: SearchResolvedFrom.remote,
              payload: SearchHitPayloadContentPost(item),
            ),
          ],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      ],
      searchRequestId: requestId,
    );
  }
}

final class _TelemetrySearchRepository implements SearchRepository {
  _TelemetrySearchRepository({this.empty = false});

  final bool empty;
  int _calls = 0;

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    final requestId = 'search-telemetry-${++_calls}';
    if (empty) {
      return SearchResponse(
        request: normalized,
        searchRequestId: requestId,
        sections: const <SearchSection>[],
      );
    }
    final contentType =
        normalized.contentTypes.contains(SearchContentTypeFilter.video)
        ? 'video'
        : normalized.contentTypes.contains(SearchContentTypeFilter.article)
        ? 'article'
        : 'image';
    final item = PostSearchItemView(
      postId: 'post-telemetry-$_calls',
      contentType: contentType,
      contentIdentity: contentType == 'article' ? 'article' : 'work',
      title: '可观测摄影作品 $_calls',
      authorDisplayName: '漏斗测试作者',
    );
    return SearchResponse(
      request: normalized,
      searchRequestId: requestId,
      sections: <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: <SearchHit>[
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: item.postId,
              title: item.title ?? item.postId,
              rankPosition: 1,
              resolvedFrom: SearchResolvedFrom.remote,
              payload: SearchHitPayloadContentPost(item),
            ),
          ],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      ],
    );
  }
}

class _FakeNetworkSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.objectTypes.length > 1) {
      final responses = await Future.wait<SearchResponse>(
        normalized.objectTypes.map(
          (objectType) => search(
            SearchRequest(
              query: normalized.query,
              mode: normalized.mode,
              objectTypes: <SearchObjectType>{objectType},
              limit: normalized.limit,
              contentTypes: normalized.contentTypes,
              categoryId: normalized.categoryId,
              subCategory: normalized.subCategory,
            ),
            cancellation: cancellation,
            deadlineAt: deadlineAt,
          ),
        ),
      );
      final sections = <SearchSection>[];
      final sectionIds = <String>{};
      for (final response in responses) {
        for (final section in response.sections) {
          if (sectionIds.add(section.id)) sections.add(section);
        }
      }
      return SearchResponse(
        request: normalized,
        sections: sections,
        relatedTerms: <String>['${normalized.query} 攻略', '街头摄影'],
      );
    }
    if (normalized.objectTypes.contains(SearchObjectType.contentPost)) {
      final wantsArticle = normalized.contentTypes.contains(
        SearchContentTypeFilter.article,
      );
      final item = PostSearchItemView(
        postId: 'fake_street_photo',
        contentType: wantsArticle ? 'article' : 'image',
        contentIdentity: wantsArticle ? 'article' : 'work',
        title: '街头摄影',
        summary: '摄影频道结果',
        coverUrl:
            'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
        authorDisplayName: '街头摄影',
        categoryId: normalized.categoryId ?? 'photography',
        subCategory: '影像',
        likeCount: 32,
        matchedField: 'author',
      );
      return SearchResponse(
        request: normalized,
        sections: <SearchSection>[
          SearchSection(
            id: 'content',
            title: '内容',
            objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.contentPost,
                objectId: item.postId,
                title: item.title ?? item.postId,
                subtitle: item.authorDisplayName,
                snippet: item.summary,
                resolvedFrom: SearchResolvedFrom.remote,
                matchedField: item.matchedField,
                payload: SearchHitPayloadContentPost(item),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    if (normalized.objectTypes.contains(SearchObjectType.circleGroup) ||
        normalized.objectTypes.contains(SearchObjectType.circleCircle)) {
      return SearchResponse(
        request: normalized,
        sections: <SearchSection>[
          SearchSection(
            id: 'groups',
            title: '讨论',
            objectTypes: const <SearchObjectType>[
              SearchObjectType.circleGroup,
              SearchObjectType.circleCircle,
            ],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.circleGroup,
                objectId: 'group_light_photo',
                title: '光影摄影社主群',
                subtitle: '圈子主群',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: const SearchHitPayloadCircleGroup(
                  CircleSearchItemView(
                    circleId: 'fixture_circle_photo',
                    name: '光影摄影社主群',
                    description: '圈子主群',
                    circleName: '光影摄影社',
                    memberCount: 0,
                    postCount: 0,
                  ),
                ),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    if (normalized.objectTypes.contains(SearchObjectType.chatConversation) ||
        normalized.objectTypes.contains(SearchObjectType.chatMessage)) {
      return SearchResponse(
        request: normalized,
        sections: <SearchSection>[
          SearchSection(
            id: 'chat_records',
            title: '聊天记录',
            objectTypes: const <SearchObjectType>[
              SearchObjectType.chatConversation,
              SearchObjectType.chatMessage,
            ],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.chatMessage,
                objectId: 'msg_west_lake',
                title: '西湖摄影讨论',
                subtitle: '光影摄影社主群',
                snippet: '周末西湖拍摄路线和集合时间',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadChatMessage(
                  MessageSearchItemView(
                    messageId: 'msg_west_lake',
                    conversationId: 'group_light_photo',
                    conversationTitle: '西湖摄影讨论',
                    messageType: 'text',
                    contentPreview: '周末西湖拍摄路线和集合时间',
                    timestamp: DateTime.utc(2026, 7, 20),
                  ),
                ),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    if (normalized.objectTypes.contains(SearchObjectType.entityHomepage) ||
        normalized.objectTypes.contains(SearchObjectType.locationPlace)) {
      // 顶卡云侧单源：entity.homepage（已绑定实体主页）。一方地点 location.place
      // 仅在 connectionState=connected 时进交集「已形成的连接」。
      final sections = <SearchSection>[];
      if (normalized.objectTypes.contains(SearchObjectType.entityHomepage)) {
        sections.add(
          const SearchSection(
            id: 'homepages',
            title: '主页',
            objectTypes: <SearchObjectType>[SearchObjectType.entityHomepage],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.entityHomepage,
                objectId: 'homepage_west_lake',
                title: '西湖',
                subtitle: '杭州',
                snippet: '杭州热门地点',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadEntityHomepage(
                  SearchEntityHomepageHitView(
                    homepageId: 'homepage_west_lake',
                    name: '西湖',
                    placeName: '杭州',
                    followerCount: 1200,
                    contentCount: 340,
                  ),
                ),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        );
      }
      if (normalized.objectTypes.contains(SearchObjectType.locationPlace)) {
        sections.add(
          const SearchSection(
            id: 'locations',
            title: '位置',
            objectTypes: <SearchObjectType>[SearchObjectType.locationPlace],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.locationPlace,
                objectId: 'place_west_lake_alley',
                title: '西湖旁断桥小巷',
                subtitle: '杭州',
                snippet: '被内容引用但未绑定主页的自由文本地点',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadLocationPlace(
                  SearchLocationPlaceHitView(
                    placeId: 'place_west_lake_alley',
                    name: '西湖旁断桥小巷',
                  ),
                ),
                connectionState: 'connected',
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        );
      }
      return SearchResponse(request: normalized, sections: sections);
    }
    if (normalized.objectTypes.contains(SearchObjectType.userProfile)) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[
          SearchSection(
            id: 'users',
            title: '人',
            objectTypes: <SearchObjectType>[SearchObjectType.userProfile],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.userProfile,
                objectId: 'user_photo_friend',
                title: '林同学',
                subtitle: '摄影爱好者',
                snippet: '摄影同好',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadUserProfile(
                  SearchUserProfileHitView(
                    userId: 'user_photo_friend',
                    displayName: '林同学',
                    bio: '摄影爱好者',
                  ),
                ),
              ),
              SearchHit(
                objectType: SearchObjectType.userProfile,
                objectId: 'user_new_photo',
                title: '新摄影师',
                subtitle: '同城影像',
                snippet: '同城影像创作',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadUserProfile(
                  SearchUserProfileHitView(
                    userId: 'user_new_photo',
                    displayName: '新摄影师',
                    bio: '同城影像',
                  ),
                ),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    return const SearchResponse(
      request: SearchRequest(query: ''),
      sections: <SearchSection>[],
    );
  }
}

class _RecordingCanonicalSearchRepository implements SearchRepository {
  final List<SearchRequest> requests = <SearchRequest>[];
  final _FakeNetworkSearchRepository _delegate = _FakeNetworkSearchRepository();

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    requests.add(request.normalized());
    return _delegate.search(
      request,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }
}

/// 交集消费契约 fake：内容命中携带云侧 connectionState 闭集与 intersectionReason
/// 子集（primaryText），用于验证端只读 primaryText、按 connectionState 分组、
/// 无 primaryText 不拼装交集句。
class _IntersectionContractSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (!normalized.objectTypes.contains(SearchObjectType.contentPost)) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    const connected = PostSearchItemView(
      postId: 'post_connected_liked',
      contentType: 'image',
      contentIdentity: 'work',
      title: '你点赞过的海边日落',
      summary: '已互动内容',
      coverUrl:
          'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=800',
      authorDisplayName: '海边摄影师',
      connectionState: 'connected',
      likeCount: 42,
    );
    final leadWithPrimary = PostSearchItemView(
      postId: 'post_lead_primary',
      contentType: 'image',
      contentIdentity: 'work',
      title: '环岛路骑行机位合集',
      summary: '交集线索内容',
      coverUrl:
          'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800',
      authorDisplayName: '骑行小林',
      connectionState: 'intersection_lead',
      intersectionReason: IntersectionReason(
        primaryText: '你关注的小林也在拍这里',
        dimension: 'sharedFollowees',
        intersectionClass: 'fact',
      ),
    );
    const discoveryNoPrimary = PostSearchItemView(
      postId: 'post_discovery_plain',
      contentType: 'article',
      contentIdentity: 'article',
      title: '城市天际线拍摄攻略',
      summary: '未连接且无交集句内容',
      coverUrl:
          'https://images.unsplash.com/photo-1519046904884-53103b34b206?w=800',
      authorDisplayName: '攻略君',
      connectionState: 'unconnected',
    );
    return SearchResponse(
      request: normalized,
      sections: <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: <SearchHit>[
            for (final view in <PostSearchItemView>[
              connected,
              leadWithPrimary,
              discoveryNoPrimary,
            ])
              SearchHit(
                objectType: SearchObjectType.contentPost,
                objectId: view.postId,
                title: view.title ?? view.postId,
                snippet: view.summary,
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadContentPost(view),
              ),
          ],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      ],
    );
  }
}

class _DegradedNetworkSearchRepository extends _FakeNetworkSearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final base = await super.search(request);
    return SearchResponse(
      request: base.request,
      sections: base.sections,
      degradeSignals: const <SearchDegradeSignal>[
        SearchDegradeSignal(
          code: 'circle_group_remote_empty',
          message: 'circle.group 远端返回空结果，准备回退本地快照。',
          objectType: SearchObjectType.circleGroup,
        ),
      ],
    );
  }
}

class _EmptyNetworkSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return SearchResponse(
      request: request.normalized(),
      sections: const <SearchSection>[],
      relatedTerms: const <String>['摄影', '旅行'],
    );
  }
}

class _EmptyDegradedNetworkSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return SearchResponse(
      request: request,
      sections: const <SearchSection>[],
      degradeSignals: const <SearchDegradeSignal>[
        SearchDegradeSignal(
          code: 'circle_group_remote_empty',
          message: 'circle.group 远端返回空结果，准备回退本地快照。',
          objectType: SearchObjectType.circleGroup,
        ),
      ],
    );
  }
}
