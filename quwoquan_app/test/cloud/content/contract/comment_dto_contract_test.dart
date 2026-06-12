import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

void main() {
  group('CommentDto — 常规契约', () {
    test('fromMap 解析评论增强字段', () {
      final raw = <String, dynamic>{
        '_id': 'comment_001',
        'postId': 'post_001',
        'authorId': 'user_001',
        'authorDisplayNameSnapshot': '评论作者',
        'authorAvatarUrlSnapshot': 'https://example.com/avatar.jpg',
        'content': '这是一条评论',
        'attachmentMediaIds': <String>['media_001'],
        'attachments': <Map<String, dynamic>>[
          <String, dynamic>{
            'mediaId': 'media_001',
            'type': 'image',
            'url': 'https://example.com/comment.jpg',
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
        'canonicalEntityId': 'entity:homepage:westlake',
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
        'postSummary': <String, dynamic>{
          'postId': 'post_001',
          'title': '帖子标题',
        },
        'likeCount': 5,
        'dislikeCount': 1,
        'viewerReaction': 'like',
        'recommendedScore': 0.98,
        'status': 'visible',
        'isAuthor': true,
        'canDelete': true,
        'canReply': true,
        'canReport': false,
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
      expect(dto.canonicalEntityId, equals('entity:homepage:westlake'));
      expect(dto.assistantMentioned, isTrue);
      expect(dto.assistantReplySource, equals('user_mention'));
      expect(dto.assistantCorrectionStatus, equals('pending'));
      expect(dto.replyPreview, hasLength(1));
      expect(dto.replyPreview.single.id, equals('comment_reply_001'));
      expect(dto.personaContextVersion, equals(3));
    });

    test('toMap round-trip 保持评论增强字段', () {
      final dto = CommentDto.fromMap(<String, dynamic>{
        '_id': 'comment_rt',
        'postId': 'post_001',
        'authorId': 'user_001',
        'content': 'round trip',
        'entityRefs': <String>['entity:poi:westlake'],
        'primaryHomepageId': 'homepage_westlake',
        'canonicalEntityId': 'entity:homepage:westlake',
        'assistantMentioned': true,
        'assistantReplySource': 'quality_boost',
        'assistantCorrectionStatus': 'corrected',
        'createdAt': '2026-06-01T12:00:00Z',
      });

      final map = dto.toMap();

      expect(map['entityRefs'], equals(<String>['entity:poi:westlake']));
      expect(map['primaryHomepageId'], equals('homepage_westlake'));
      expect(map['canonicalEntityId'], equals('entity:homepage:westlake'));
      expect(map['assistantMentioned'], isTrue);
      expect(map['assistantReplySource'], equals('quality_boost'));
      expect(map['assistantCorrectionStatus'], equals('corrected'));
    });
  });
}
