import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/features/chat/pages/chat_detail_page.dart';

class _AssistantUiTestRepository implements AppContentRepository {
  _AssistantUiTestRepository(this._messages);

  final MockAppContentRepository _delegate = MockAppContentRepository();
  final List<Map<String, dynamic>> _messages;

  @override
  List<Map<String, dynamic>> chatMessagesFor(String conversationId) {
    if (conversationId == AppConceptConstants.assistantConversationId) {
      return _messages;
    }
    return _delegate.chatMessagesFor(conversationId);
  }

  @override
  Map<String, dynamic>? articleById(String id) => _delegate.articleById(id);
  @override
  List<Map<String, dynamic>> get assistantMemoryData => _delegate.assistantMemoryData;
  @override
  List<Map<String, dynamic>> get assistantSkillsData => _delegate.assistantSkillsData;
  @override
  List<Map<String, dynamic>> get assistantTasksData => _delegate.assistantTasksData;
  @override
  Map<String, dynamic> get chatAssistantConversation => _delegate.chatAssistantConversation;
  @override
  List<Map<String, dynamic>> get chatEncryptedConversations =>
      _delegate.chatEncryptedConversations;
  @override
  List<Map<String, dynamic>> get chatMockContactCircles => _delegate.chatMockContactCircles;
  @override
  List<Map<String, dynamic>> get chatMockContactGroups => _delegate.chatMockContactGroups;
  @override
  List<Map<String, dynamic>> get chatMockContacts => _delegate.chatMockContacts;
  @override
  List<Map<String, dynamic>> get chatMockConversations => _delegate.chatMockConversations;
  @override
  List<Map<String, dynamic>> get chatMockConversationsAtMe =>
      _delegate.chatMockConversationsAtMe;
  @override
  Map<String, dynamic> get circlePageCircleInfo => _delegate.circlePageCircleInfo;
  @override
  Map<String, Map<String, dynamic>> get circlesCategoryConfig =>
      _delegate.circlesCategoryConfig;
  @override
  List<Map<String, dynamic>> get circlesMockActivities => _delegate.circlesMockActivities;
  @override
  List<Map<String, dynamic>> get circlesMockCircles => _delegate.circlesMockCircles;
  @override
  List<Map<String, dynamic>> get discoveryArticleData => _delegate.discoveryArticleData;
  @override
  List<Map<String, dynamic>> get discoveryMomentData => _delegate.discoveryMomentData;
  @override
  List<Map<String, dynamic>> get discoveryPhotoData => _delegate.discoveryPhotoData;
  @override
  List<Map<String, dynamic>> get discoveryVideoData => _delegate.discoveryVideoData;
  @override
  Map<String, dynamic> get helperReadSummary => _delegate.helperReadSummary;
}

/// L1b Widget 测试：chat 领域 chat_detail 页面的助理 UI 回归
///
/// 领域：ui/chat，业务对象：chat_detail
void main() {
  testWidgets('助理时间线与参考资料卡片正常渲染', (tester) async {
    final repository = _AssistantUiTestRepository(<Map<String, dynamic>>[
      <String, dynamic>{
        'id': 'assistant_msg_1',
        'conversationId': AppConceptConstants.assistantConversationId,
        'type': 'text',
        'content': '这是测试回答',
        'senderId': AppConceptConstants.assistantSenderId,
        'senderName': AppConceptConstants.assistantLabel,
        'senderAvatar': '',
        'timestamp': '10:10',
        'isRead': true,
        'isSelf': false,
        'uiTimeline': <Map<String, dynamic>>[
          <String, dynamic>{'event': 'thinking'},
          <String, dynamic>{'event': 'keyword_search'},
          <String, dynamic>{'event': 'reference_increment'},
        ],
        'uiReferences': <Map<String, dynamic>>[],
      },
    ]);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appContentRepositoryProvider.overrideWithValue(repository),
        ],
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, child) => MaterialApp(
            locale: const Locale('zh'),
            home: ChatDetailPage(
              conversationId: AppConceptConstants.assistantConversationId,
              onBack: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.assistantTimelineSearchProcess),
      findsOneWidget,
      reason: '无参考资料时标题为「搜索过程」',
    );
    await tester.tap(find.text(UITextConstants.assistantTimelineSearchProcess));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.assistantTimelineThinking), findsOneWidget);
    expect(find.text(UITextConstants.assistantTimelineKeywordSearch), findsOneWidget);
    expect(find.text(UITextConstants.assistantTimelineReferenceIncrement), findsOneWidget);
  });

  testWidgets('非白名单外链点击时拦截并提示', (tester) async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SystemChannels.platform.setMockMethodCallHandler((MethodCall methodCall) async {
      if (methodCall.method == 'Clipboard.setData') return null;
      return null;
    });
    const refTitle = '外部来源';
    final repository = _AssistantUiTestRepository(<Map<String, dynamic>>[
      <String, dynamic>{
        'id': 'assistant_msg_2',
        'conversationId': AppConceptConstants.assistantConversationId,
        'type': 'text',
        'content': '参考如下',
        'senderId': AppConceptConstants.assistantSenderId,
        'senderName': AppConceptConstants.assistantLabel,
        'senderAvatar': '',
        'timestamp': '10:20',
        'isRead': true,
        'isSelf': false,
        'uiTimeline': <Map<String, dynamic>>[
          <String, dynamic>{'event': 'reference_ready'},
        ],
        'uiReferences': <Map<String, dynamic>>[
          <String, dynamic>{
            'title': refTitle,
            'url': 'https://unsafe-example.com/data',
          },
        ],
      },
    ]);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appContentRepositoryProvider.overrideWithValue(repository),
        ],
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, child) => MaterialApp(
            locale: const Locale('zh'),
            home: ChatDetailPage(
              conversationId: AppConceptConstants.assistantConversationId,
              onBack: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text(UITextConstants.assistantTimelineReferenceCount.replaceFirst('%s', '1')));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.textContaining(refTitle));
    await tester.tap(find.textContaining(refTitle));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.text(UITextConstants.assistantReferenceHostBlocked),
      findsOneWidget,
      reason: '点击非白名单外链后应显示拦截提示',
    );
  });
}
