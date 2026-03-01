import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/media/image/viewer/immersive_image_viewer.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';

/// D14：微趣媒体浏览器 UI 回归 — feedPosts、二维导航、文字 3 行+全文展开
///
/// 特性树：moment-display-journey
PostSummaryView _momentPost({
  required String id,
  required String body,
  List<String> images = const ['https://example.com/img1.jpg'],
}) {
  final dto = MomentPostDto(
    id: id,
    type: 'moment',
    authorId: 'u1',
    displayName: '测试用户',
    avatarUrl: 'https://example.com/avatar.jpg',
    body: body,
    imageUrls: images,
    likeCount: 0,
    commentCount: 0,
    favoriteCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
  );
  return PostSummaryView.fromDto(dto);
}

Widget _wrap(Widget child) {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(375, 812),
      builder: (context, _) => MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(body: child),
      ),
    ),
  );
}

void _consumeImageLoadExceptions(WidgetTester tester) {
  while (tester.takeException() != null) {
    // 消费测试中网络图片加载的 400 异常
  }
}

void main() {
  group('MomentMediaViewer — 渲染契约', () {
    testWidgets('nested 模式多 post 渲染', (tester) async {
      final posts = [
        _momentPost(id: 'm1', body: '微趣1', images: ['https://ex.com/a.jpg']),
        _momentPost(id: 'm2', body: '微趣2', images: ['https://ex.com/b.jpg']),
      ];

      await tester.pumpWidget(_wrap(
        ImmersiveImageViewer(
          isOpen: true,
          onClose: () {},
          mediaItems: const [],
          initialIndex: 0,
          posts: posts,
          initialPostIndex: 0,
          initialImageIndex: 0,
          layoutMode: 'nested',
          onUserClick: (_, {String? avatarUrl, String? displayName, String? backgroundUrl}) {},
        ),
      ));
      await tester.pump();
      _consumeImageLoadExceptions(tester);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      expect(find.byType(ImmersiveImageViewer), findsOneWidget);
      expect(find.byType(PageView), findsWidgets);
    });

    testWidgets('nested 模式单 post 多图渲染', (tester) async {
      final posts = [
        _momentPost(
          id: 'm1',
          body: '多图微趣',
          images: [
            'https://ex.com/1.jpg',
            'https://ex.com/2.jpg',
          ],
        ),
      ];

      await tester.pumpWidget(_wrap(
        ImmersiveImageViewer(
          isOpen: true,
          onClose: () {},
          mediaItems: const [],
          initialIndex: 0,
          posts: posts,
          initialPostIndex: 0,
          initialImageIndex: 1,
          layoutMode: 'nested',
          onUserClick: (_, {String? avatarUrl, String? displayName, String? backgroundUrl}) {},
        ),
      ));
      await tester.pump();
      _consumeImageLoadExceptions(tester);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      expect(find.byType(ImmersiveImageViewer), findsOneWidget);
    });
  });

  group('MomentMediaViewer — 文字展示契约', () {
    testWidgets('MediaCaptionBlock 超 3 行显示全文，点击展开后可滚动', (tester) async {
      const longCaption =
          '这是一段超过三行才会触发展开的长正文。需要足够多的文字才能让 MediaCaptionBlock 显示全文链接。'
          '继续添加更多文字以确保能够触发溢出检测。再来一点内容。';

      var isExpanded = false;
      await tester.pumpWidget(
        StatefulBuilder(
          builder: (context, setState) => ScreenUtilInit(
            designSize: const Size(375, 812),
            builder: (context, _) => MaterialApp(
              theme: ThemeData.dark(),
              home: Scaffold(
                body: SizedBox(
                  width: 80,
                  child: MediaCaptionBlock(
                    title: '',
                    caption: longCaption,
                    isExpanded: isExpanded,
                    onToggle: () => setState(() => isExpanded = !isExpanded),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining(UITextConstants.fullText), findsOneWidget);

      await tester.tap(find.textContaining(UITextConstants.fullText));
      await tester.pumpAndSettle();

      expect(find.textContaining(UITextConstants.collapse), findsOneWidget);
      expect(find.byType(SingleChildScrollView), findsOneWidget);
    });

    testWidgets('body 作为 caption 传入 viewer 时展示', (tester) async {
      const longBody =
          '这是一段超过三行才会触发展开的长正文。需要足够多的文字才能让 MediaCaptionBlock 显示全文链接。'
          '继续添加更多文字以确保能够触发溢出检测。再来一点。';
      final posts = [_momentPost(id: 'm1', body: longBody)];

      await tester.pumpWidget(_wrap(
        ImmersiveImageViewer(
          isOpen: true,
          onClose: () {},
          mediaItems: const [],
          initialIndex: 0,
          posts: posts,
          initialPostIndex: 0,
          layoutMode: 'nested',
          onUserClick: (_, {String? avatarUrl, String? displayName, String? backgroundUrl}) {},
        ),
      ));
      await tester.pump();
      _consumeImageLoadExceptions(tester);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // body 作为 caption 展示（3 行内不溢出时无全文链接，仅验证 caption 区域存在）
      expect(find.textContaining('这是一段超过三行'), findsOneWidget);
    });
  });

  group('MomentMediaViewer — flat 模式兼容', () {
    testWidgets('flat 模式单 post 渲染', (tester) async {
      final posts = [_momentPost(id: 'm1', body: '单条')];

      await tester.pumpWidget(_wrap(
        ImmersiveImageViewer(
          isOpen: true,
          onClose: () {},
          mediaItems: const [],
          initialIndex: 0,
          posts: posts,
          initialPostIndex: 0,
          layoutMode: 'flat',
          onUserClick: (_, {String? avatarUrl, String? displayName, String? backgroundUrl}) {},
        ),
      ));
      await tester.pump();
      _consumeImageLoadExceptions(tester);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      expect(find.byType(ImmersiveImageViewer), findsOneWidget);
    });
  });
}
