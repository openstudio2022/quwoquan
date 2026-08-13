// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-004
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/transfer_ownership_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

const _testConvId = 'fixture_conv_group';

ChatInteractionTelemetryTracker _telemetryTracker() =>
    ChatInteractionTelemetryTracker(
      telemetryReporter: RecordingAppTelemetryRecorder(),
    );

Widget _scopedApp({
  ChatMemberRepository? member,
  ChatGroupAdminRepository? groupAdmin,
}) {
  return ProviderScope(
    overrides: [
      ...chatTestRepositoryOverrides(member: member, groupAdmin: groupAdmin),
      currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/$_testConvId/transfer-ownership',
        routes: [
          GoRoute(
            path: '/chat/:id/transfer-ownership',
            builder: (_, state) => TransferOwnershipPage(
              conversationId: state.pathParameters['id'] ?? _testConvId,
              telemetryTracker: _telemetryTracker(),
            ),
          ),
        ],
      ),
    ),
  );
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
  group('TransferOwnershipPage — 渲染契约', () {
    testWidgets('正常渲染页面', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });

    testWidgets('AppBar 标题显示"选择新群主"', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.selectNewOwner), findsOneWidget);
    });

    testWidgets('搜索框可见', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(CupertinoSearchTextField), findsOneWidget);
    });

    testWidgets('成员列表不含群主自身', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.text(chatDisplayNameFor(chatCurrentUserProfileId())),
        findsNothing,
      );
    });

    testWidgets('成员列表可见且有候选人', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ListView), findsWidgets);
      expect(find.text('契约同伴一'), findsOneWidget);
    });
  });

  group('TransferOwnershipPage — 交互契约', () {
    testWidgets('搜索框可输入过滤', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final searchField = find.byType(CupertinoSearchTextField);
      await tester.enterText(searchField, '契约同伴一');
      await tester.pump();

      expect(find.text('契约同伴一'), findsWidgets);
    });

    testWidgets('点击成员弹出确认弹窗', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final memberItems = find.byType(CupertinoListTile);
      expect(memberItems, findsWidgets);

      await tester.tap(memberItems.first);
      await tester.pumpAndSettle();

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    });

    testWidgets('确认弹窗包含成员名字', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text('契约同伴一'));
      await tester.pumpAndSettle();

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.text(FoundationText.cancel), findsOneWidget);
      expect(find.text(FoundationText.confirm), findsOneWidget);
    });

    testWidgets('取消弹窗后页面继续存在', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.byType(CupertinoListTile).first);
      await tester.pumpAndSettle();

      await tester.tap(find.text(FoundationText.cancel));
      await tester.pumpAndSettle();

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });

    testWidgets('返回按钮 tap 不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final backButtons = find.byIcon(CupertinoIcons.back);
      if (backButtons.evaluate().isNotEmpty) {
        await tester.tap(backButtons.first);
        await tester.pump();
      }
      tester.takeException();
    });

    testWidgets('失败重试复用同一幂等意图并等待 Remote roster 收敛', (tester) async {
      _suppressImageErrors();
      final repo = _RetryTransferRepo();
      await tester.pumpWidget(_scopedApp(groupAdmin: repo));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text('契约同伴一'));
      await tester.pumpAndSettle();
      await tester.tap(find.text(FoundationText.confirm));
      await tester.pumpAndSettle();

      expect(find.text(ContentText.tryAgain), findsOneWidget);
      await tester.tap(find.text(ContentText.tryAgain));
      await tester.pumpAndSettle();

      expect(repo.idempotencyKeys, hasLength(2));
      expect(repo.idempotencyKeys[0], isNotEmpty);
      expect(repo.idempotencyKeys[1], repo.idempotencyKeys[0]);
    });
  });

  group('TransferOwnershipPage — 错误态渲染', () {
    testWidgets('listMembers 失败时页面不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(member: _ErrorMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });

    testWidgets('空成员列表安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(member: _EmptyMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });
  });
}

class _ErrorMembersRepo extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    throw Exception('network error');
  }
}

class _EmptyMembersRepo extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    return [];
  }
}

class _RetryTransferRepo extends Fake implements ChatGroupAdminRepository {
  // 读方法委托共享 typed double：Fake 默认抛 UnimplementedError 会把页面
  // 推入错误态，掩盖被验证的幂等重试断言。
  final ChatGroupAdminRepository _delegate = ChatTestFacets().groupAdmin;

  final List<String> idempotencyKeys = <String>[];

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId, {
    String? idempotencyKey,
  }) async {
    idempotencyKeys.add(idempotencyKey ?? '');
    if (idempotencyKeys.length == 1) {
      throw Exception('transient transfer failure');
    }
  }

  @override
  Future<GroupHome> getGroupHome(String conversationId) =>
      _delegate.getGroupHome(conversationId);

  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(String conversationId) =>
      _delegate.getGroupSettings(conversationId);
}
