import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

class _FakeShareActionHandler implements ContentShareActionHandler {
  final List<String> executed = <String>[];

  _FakeShareActionHandler();

  @override
  Future<ContentShareActionResult> execute(
    BuildContext context,
    ContentShareTemplate template,
    ContentShareAction action,
  ) async {
    executed.add(action.id);
    return ContentShareActionResult(
      actionId: action.id,
      success: true,
      dismissed: false,
    );
  }
}

void main() {
  testWidgets('点滴分享模板展示 identity actions 与时间语境', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      post: MomentPostDto(
        id: 'moment_1',
        type: 'micro',
        identity: 'moment',
        assistantUsePolicy: 'inherit',
        authorId: 'user_1',
        displayName: '阿宁',
        avatarUrl: '',
        body: '清晨六点的光，刚好落在湖面。',
        imageUrls: const ['https://example.com/moment.jpg'],
        likeCount: 8,
        commentCount: 2,
        favoriteCount: 3,
        shareCount: 1,
        createdAt: DateTime(2026, 3, 12, 6, 0),
      ),
      enableIdentityTemplate: true,
      visibility: 'public',
      circleNames: const ['晨拍圈'],
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.profileId, 'moment');
    expect(template.deeplink, 'quwoquan://content/post/moment_1');
    expect(find.text(UITextConstants.shareTemplateMomentTitle), findsOneWidget);
    expect(find.text(UITextConstants.copyLink), findsOneWidget);
    expect(find.text(UITextConstants.shareActionSavePoster), findsOneWidget);
    expect(find.text(UITextConstants.shareActionSystemShare), findsOneWidget);
    expect(find.textContaining('晨拍圈'), findsOneWidget);
    expect(find.textContaining('2026-03-12'), findsOneWidget);
  });

  testWidgets('点击分享动作会委托给 handler 并触发完成回调', (tester) async {
    final handler = _FakeShareActionHandler();
    final completed = <String>[];
    final template = ContentShareTemplateBuilder.build(
      post: MomentPostDto(
        id: 'moment_action',
        type: 'micro',
        identity: 'moment',
        assistantUsePolicy: 'inherit',
        authorId: 'user_action',
        displayName: '小悠',
        avatarUrl: '',
        body: '点击复制链接应该走真实 handler',
        imageUrls: const <String>[],
        likeCount: 0,
        commentCount: 0,
        favoriteCount: 0,
        shareCount: 0,
        createdAt: DateTime(2026, 3, 12, 10, 0),
      ),
      enableIdentityTemplate: true,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ContentShareSheet(
            template: template,
            actionHandler: handler,
            onActionCompleted: (result) async {
              completed.add(result.actionId);
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text(UITextConstants.copyLink));
    await tester.pump();

    expect(handler.executed, equals(<String>['copy_link']));
    expect(completed, equals(<String>['copy_link']));
  });

  testWidgets('默认复制链接动作会写入剪贴板', (tester) async {
    String? copiedText;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copiedText = (call.arguments as Map?)?['text']?.toString();
        }
        return null;
      },
    );
    addTearDown(() {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      );
    });

    final template = ContentShareTemplateBuilder.build(
      post: MomentPostDto(
        id: 'moment_clipboard',
        type: 'micro',
        identity: 'moment',
        assistantUsePolicy: 'inherit',
        authorId: 'user_clipboard',
        displayName: '阿遥',
        avatarUrl: '',
        body: '复制链接测试',
        imageUrls: const <String>[],
        likeCount: 0,
        commentCount: 0,
        favoriteCount: 0,
        shareCount: 0,
        createdAt: DateTime(2026, 3, 12, 11, 0),
      ),
      enableIdentityTemplate: true,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () async {
                await const DefaultContentShareActionHandler().execute(
                  context,
                  template,
                  const ContentShareAction(
                    id: 'copy_link',
                    label: UITextConstants.copyLink,
                  ),
                );
              },
              child: const Text('trigger'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('trigger'));
    await tester.pump();

    expect(copiedText, template.deeplink);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });

  testWidgets('作品圈内可见分享生成受控链接并保留标签', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      post: ArticlePostDto(
        id: 'work_1',
        type: 'article',
        identity: 'work',
        assistantUsePolicy: 'inherit',
        authorId: 'user_2',
        displayName: '洛白',
        avatarUrl: '',
        title: '城市夜拍攻略',
        body: '从机位、快门到后期流程，适合第一次扫街的摄影爱好者。',
        summary: '从机位、快门到后期流程，适合第一次扫街的摄影爱好者。',
        coverUrl: 'https://example.com/work.jpg',
        articleTemplate: 'tech',
        articleFontPreset: 'mono',
        articlePresentationVersion: 1,
        likeCount: 12,
        commentCount: 4,
        favoriteCount: 9,
        shareCount: 3,
        createdAt: DateTime(2026, 3, 12, 20, 0),
      ),
      enableIdentityTemplate: true,
      visibility: 'circle-visible',
      tags: const ['攻略', '夜景'],
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.profileId, 'work');
    expect(template.deeplink, 'quwoquan://content/post/work_1?scope=circle');
    expect(find.text(UITextConstants.shareTemplateWorkTitle), findsOneWidget);
    expect(
      find.text(UITextConstants.shareCircleVisibilityNotice),
      findsOneWidget,
    );
    expect(find.textContaining('#攻略 #夜景'), findsOneWidget);
  });

  testWidgets('私密内容会被分享模板拦截', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      post: ArticlePostDto(
        id: 'private_1',
        type: 'article',
        identity: 'work',
        assistantUsePolicy: 'inherit',
        authorId: 'user_3',
        displayName: '周周',
        avatarUrl: '',
        title: '仅自己可见',
        body: '这是一条私密内容。',
        summary: '这是一条私密内容。',
        coverUrl: '',
        articleTemplate: 'gentle',
        articleFontPreset: 'clean',
        articlePresentationVersion: 1,
        likeCount: 0,
        commentCount: 0,
        favoriteCount: 0,
        shareCount: 0,
        createdAt: DateTime(2026, 3, 12, 12, 0),
      ),
      enableIdentityTemplate: true,
      visibility: 'private',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.isBlocked, isTrue);
    expect(
      find.text(UITextConstants.sharePrivateBlocked),
      findsAtLeastNWidgets(1),
    );
    expect(find.text(UITextConstants.copyLink), findsNothing);
  });

  testWidgets('关闭 identity share flag 后回退到通用分享面板', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      post: MomentPostDto(
        id: 'legacy_1',
        type: 'micro',
        identity: 'moment',
        assistantUsePolicy: 'inherit',
        authorId: 'user_4',
        displayName: '南栀',
        avatarUrl: '',
        body: '回退到通用分享面板',
        imageUrls: const <String>[],
        likeCount: 0,
        commentCount: 0,
        favoriteCount: 0,
        shareCount: 0,
        createdAt: DateTime(2026, 3, 12, 9, 0),
      ),
      enableIdentityTemplate: false,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.isIdentityTemplate, isFalse);
    expect(
      find.text(UITextConstants.shareLegacyFallbackNotice),
      findsAtLeastNWidgets(1),
    );
    expect(find.text(UITextConstants.copyLink), findsOneWidget);
    expect(find.text(UITextConstants.shareActionSavePoster), findsNothing);
  });
}
