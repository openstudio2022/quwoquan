import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/rtc/pages/call_participant_picker_page.dart';

class _MockAppDataSourceModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;
}

class _PickerChatRepository extends MockChatRepository {
  static const ChatInboxDto _inbox002 = ChatInboxDto(
    id: 'conv_002',
    type: 'group',
    title: '当前群聊',
    avatarUrl: '',
    avatarCompositeUrls: [],
    lastMessagePreview: '',
    lastMessageType: 'text',
    lastSeq: 0,
    unreadCount: 0,
    mentionUnreadCount: 0,
    muted: false,
    pinned: false,
  );
  static const ChatInboxDto _inbox003 = ChatInboxDto(
    id: 'conv_003',
    type: 'group',
    title: '摄影同好群',
    avatarUrl: '',
    avatarCompositeUrls: [],
    lastMessagePreview: '',
    lastMessageType: 'text',
    lastSeq: 0,
    unreadCount: 0,
    mentionUnreadCount: 0,
    muted: false,
    pinned: false,
  );

  @override
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = 20,
  }) async {
    return const [_inbox002, _inbox003];
  }

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return <Map<String, dynamic>>[
      {
        '_id': 'conv_002',
        'id': 'conv_002',
        'type': 'group',
        'title': '当前群聊',
        'memberCount': 4,
      },
      {
        '_id': 'conv_003',
        'id': 'conv_003',
        'type': 'group',
        'title': '摄影同好群',
        'memberCount': 3,
      },
    ];
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    if (conversationId == 'conv_002') {
      return const [
        ChatConversationMemberDto(
          userId: 'user_002',
          displayName: '当前群成员 A',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
        ChatConversationMemberDto(
          userId: 'user_003',
          displayName: '当前群成员 B',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
      ];
    }
    if (conversationId == 'conv_003') {
      return const [
        ChatConversationMemberDto(
          userId: 'user_004',
          displayName: '跨群成员 A',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
        ChatConversationMemberDto(
          userId: 'user_005',
          displayName: '跨群成员 B',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
      ];
    }
    return const [];
  }

  @override
  Future<List<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    return const [
      ChatContactRowDto(
        userId: 'user_006',
        displayName: '同好小雨',
        avatarUrl: '',
      ),
      ChatContactRowDto(
        userId: 'user_007',
        displayName: '同好阿青',
        avatarUrl: '',
      ),
    ];
  }
}

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final msg = details.exception.toString();
    if (msg.contains('HTTP request failed') ||
        msg.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  group('CallParticipantPickerPage — 渲染契约', () {
    testWidgets('群聊场景显示来源切换：当前会话 / 同好 / 其他群', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              _MockAppDataSourceModeNotifier.new,
            ),
            chatRepositoryProvider.overrideWithValue(_PickerChatRepository()),
          ],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(conversationId: 'conv_002'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('当前会话'), findsOneWidget);
      expect(find.text('同好'), findsOneWidget);
      expect(find.text('其他群'), findsOneWidget);
    });

    testWidgets('切换到其他群后显示可切换的群来源与对应成员', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              _MockAppDataSourceModeNotifier.new,
            ),
            chatRepositoryProvider.overrideWithValue(_PickerChatRepository()),
          ],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(conversationId: 'conv_002'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('其他群'));
      await tester.pumpAndSettle();

      expect(find.text('摄影同好群'), findsOneWidget);
      await tester.tap(find.text('摄影同好群'));
      await tester.pumpAndSettle();
      expect(find.text('跨群成员 A'), findsOneWidget);
    });
  });

  group('CallParticipantPickerPage — 交互契约', () {
    testWidgets('切换到同好来源后展示同好成员', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              _MockAppDataSourceModeNotifier.new,
            ),
            chatRepositoryProvider.overrideWithValue(_PickerChatRepository()),
          ],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(conversationId: 'conv_002'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('同好'));
      await tester.pumpAndSettle();

      expect(find.text('同好小雨'), findsOneWidget);
      expect(find.text('同好阿青'), findsOneWidget);
    });
  });

  group('CallParticipantPickerPage — 错误态渲染', () {
    testWidgets('群来源为空时页面仍安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              _MockAppDataSourceModeNotifier.new,
            ),
            chatRepositoryProvider.overrideWithValue(_PickerChatRepository()),
          ],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(conversationId: 'conv_missing'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('邀请参与者'), findsOneWidget);
    });
  });
}
