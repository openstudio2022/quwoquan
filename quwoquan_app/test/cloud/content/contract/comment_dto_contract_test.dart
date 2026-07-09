import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  group('CommentDto — 常规契约', () {
    test('fromMap 解析评论增强字段', () {
      final raw = <String, dynamic>{
        '_id': 'comment_001',
        'postId': 'post_001',
        'authorId': 'user_001',
        'authorDisplayNameSnapshot': '评论作者',
        'authorAvatarUrlSnapshot': 'https://example.com/avatar.jpg',
        'ipLocation': '浙江',
        'content': '这是一条评论',
        'attachmentMediaIds': <String>['media_001'],
        'attachments': <Map<String, dynamic>>[
          <String, dynamic>{
            'mediaId': 'media_001',
            'type': 'image',
            'url': 'https://example.com/comment.jpg',
            'thumbnailUrl': 'https://example.com/comment_thumb.jpg',
            'width': 1200,
            'height': 800,
            'moderationStatus': 'approved',
          },
        ],
        'mentions': <Map<String, dynamic>>[
          <String, dynamic>{
            'type': 'assistant',
            'targetId': 'assistant_xiaoqu',
            'displayName': '小趣',
          },
        ],
        'entityRefs': <String>['entity:poi:westlake'],
        'primaryHomepageId': 'homepage_westlake',
        'canonicalEntityId': 'entity:poi:westlake',
        'assistantMentioned': true,
        'assistantReplySource': 'user_mention',
        'assistantCorrectionStatus': 'pending',
        'replyCount': 2,
        'replyPreview': <Map<String, dynamic>>[
          <String, dynamic>{
            '_id': 'comment_reply_001',
            'postId': 'post_001',
            'authorId': 'user_002',
            'content': '这是回复',
            'createdAt': '2026-06-01T12:30:00Z',
          },
        ],
        'replyNextCursor': 'comment_reply_001',
        'postSummary': <String, dynamic>{'postId': 'post_001', 'title': '帖子标题'},
        'likeCount': 5,
        'dislikeCount': 1,
        'viewerReaction': 'like',
        'authorLiked': true,
        'recommendedScore': 0.98,
        'status': 'visible',
        'isPinned': true,
        'pinnedAt': '2026-06-02T08:00:00Z',
        'isAuthor': true,
        'canDelete': true,
        'canReply': true,
        'canReport': false,
        'canPin': true,
        'personaContextVersion': 3,
        'createdAt': '2026-06-01T12:00:00Z',
      };

      final dto = CommentDto.fromMap(raw);

      expect(dto.id, equals('comment_001'));
      expect(dto.postId, equals('post_001'));
      expect(dto.authorId, equals('user_001'));
      expect(dto.displayName, equals('评论作者'));
      expect(dto.avatarUrl, equals('https://example.com/avatar.jpg'));
      expect(dto.entityRefs, equals(<String>['entity:poi:westlake']));
      expect(dto.primaryHomepageId, equals('homepage_westlake'));
      expect(dto.canonicalEntityId, equals('entity:poi:westlake'));
      expect(dto.assistantMentioned, isTrue);
      expect(dto.assistantReplySource, equals('user_mention'));
      expect(dto.assistantCorrectionStatus, equals('pending'));
      expect(dto.replyPreview, hasLength(1));
      expect(dto.replyPreview.single.id, equals('comment_reply_001'));
      expect(dto.personaContextVersion, equals(3));

      // 净新展示字段：IP 属地 / 作者赞过 / 置顶 / 可置顶权限。
      expect(dto.ipLocation, equals('浙江'));
      expect(dto.authorLiked, isTrue);
      expect(dto.isPinned, isTrue);
      expect(dto.canPin, isTrue);
      expect(dto.pinnedAt, equals(DateTime.parse('2026-06-02T08:00:00Z')));

      // attachments 类型化（消除 Map 穿透）：契约固定字段与派生 getter。
      expect(dto.attachments, hasLength(1));
      final attachment = dto.attachments.single;
      expect(attachment, isA<CommentAttachmentDto>());
      expect(attachment.mediaId, equals('media_001'));
      expect(attachment.type, equals('image'));
      expect(attachment.url, equals('https://example.com/comment.jpg'));
      expect(
        attachment.thumbnailUrl,
        equals('https://example.com/comment_thumb.jpg'),
      );
      expect(attachment.width, equals(1200));
      expect(attachment.height, equals(800));
      expect(attachment.moderationStatus, equals('approved'));
      expect(
        attachment.displayUrl,
        equals('https://example.com/comment_thumb.jpg'),
      );
      expect(attachment.aspectRatio, closeTo(1.5, 1e-9));
    });

    test('toMap round-trip 保持评论增强字段', () {
      final dto = CommentDto.fromMap(<String, dynamic>{
        '_id': 'comment_rt',
        'postId': 'post_001',
        'authorId': 'user_001',
        'content': 'round trip',
        'entityRefs': <String>['entity:poi:westlake'],
        'primaryHomepageId': 'homepage_westlake',
        'canonicalEntityId': 'entity:poi:westlake',
        'assistantMentioned': true,
        'assistantReplySource': 'quality_boost',
        'assistantCorrectionStatus': 'corrected',
        'ipLocation': '广东',
        'authorLiked': true,
        'isPinned': true,
        'pinnedAt': '2026-06-02T08:00:00Z',
        'canPin': true,
        'attachments': <Map<String, dynamic>>[
          <String, dynamic>{
            'mediaId': 'media_rt',
            'type': 'image',
            'url': 'https://example.com/rt.jpg',
            'thumbnailUrl': 'https://example.com/rt_thumb.jpg',
            'width': 900,
            'height': 600,
            'moderationStatus': 'pending',
          },
        ],
        'createdAt': '2026-06-01T12:00:00Z',
      });

      final map = dto.toMap();

      expect(map['entityRefs'], equals(<String>['entity:poi:westlake']));
      expect(map['primaryHomepageId'], equals('homepage_westlake'));
      expect(map['canonicalEntityId'], equals('entity:poi:westlake'));
      expect(map['assistantMentioned'], isTrue);
      expect(map['assistantReplySource'], equals('quality_boost'));
      expect(map['assistantCorrectionStatus'], equals('corrected'));
      expect(map['ipLocation'], equals('广东'));
      expect(map['authorLiked'], isTrue);
      expect(map['isPinned'], isTrue);
      expect(map['canPin'], isTrue);
      expect(map['pinnedAt'], equals('2026-06-02T08:00:00.000Z'));

      final attachments = map['attachments'] as List<dynamic>;
      expect(attachments, hasLength(1));
      expect(
        attachments.single,
        equals(<String, dynamic>{
          'mediaId': 'media_rt',
          'type': 'image',
          'url': 'https://example.com/rt.jpg',
          'thumbnailUrl': 'https://example.com/rt_thumb.jpg',
          'width': 900,
          'height': 600,
          'moderationStatus': 'pending',
        }),
      );
    });

    test('CommentPage totalCount 承载同一评论集合总量', () {
      final item = CommentDto.fromMap(<String, dynamic>{
        '_id': 'comment_page_item',
        'postId': 'post_001',
        'authorId': 'user_001',
        'content': '分页项',
        'createdAt': '2026-06-01T12:00:00Z',
      });

      final page = CommentPage(
        items: <CommentDto>[item],
        nextCursor: 'cursor_1',
        totalCount: 182,
      );
      final fallbackPage = CommentPage(items: <CommentDto>[item]);

      expect(page.items, hasLength(1));
      expect(page.nextCursor, equals('cursor_1'));
      expect(page.totalCount, equals(182));
      expect(fallbackPage.totalCount, equals(1));
    });
  });
}
