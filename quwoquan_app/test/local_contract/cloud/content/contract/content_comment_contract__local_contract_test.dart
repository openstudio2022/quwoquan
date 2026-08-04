// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-004
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-010
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('ContentComment pure contract', () {
    test('严格解码商用查询投影', () {
      final page = decodeCommentPageSlice(<String, Object?>{
        'items': <Object?>[
          _wireItem(
            id: 'comment-1',
            attachments: <Object?>[
              <String, Object?>{
                'mediaId': 'asset-1',
                'mediaType': 'image',
                'url': 'https://cdn.example.com/asset-1.jpg',
                'width': 1200,
                'height': 800,
                'available': true,
              },
            ],
            replies: <Object?>[_wireItem(id: 'reply-1')],
          ),
        ],
        'nextCursor': 'cursor-2',
        'total': 8,
      });

      final item = page.items.single;
      expect(item.id, 'comment-1');
      expect(item.version, 3);
      expect(
        item.attachments.single.url.toString(),
        contains('asset-1.jpg'),
      );
      expect(item.attachments.single.width, 1200);
      expect(item.attachments.single.height, 800);
      expect(item.replyPreview.single.id, 'reply-1');
      expect(item.viewerReaction, CommentReactionType.like);
      expect(item.canDelete, isTrue);
      expect(item.canPin, isTrue);
      expect(page.nextCursor, 'cursor-2');
      expect(page.total, 8);
    });

    test('解码器对缺少商用字段 fail closed', () {
      final wire = _wireItem(id: 'comment-1')..remove('viewerReaction');
      expect(
        () => decodeCommentPageSlice(<String, Object?>{
          'items': <Object?>[wire],
          'nextCursor': null,
          'total': 1,
        }),
        throwsFormatException,
      );
    });

    test('非法枚举和宽松数字不被兼容', () {
      final wire = _wireItem(id: 'comment-1')
        ..['viewerReaction'] = 'hearted'
        ..['likeCount'] = '12';
      expect(
        () => decodeCommentPageSlice(<String, Object?>{
          'items': <Object?>[wire],
          'nextCursor': null,
          'total': 1,
        }),
        throwsFormatException,
      );
    });

    test('typed command 只编码业务载荷', () {
      final payload = encodeContentCommentCreateCommentGeneratedRequest(
        CreateContentCommentCommand(
          postId: 'post-1',
          content: '端云对象闭环',
          replyToCommentId: 'comment-root',
          attachmentMediaIds: const <String>['asset-1'],
          mentions: <CommentMention>[
            CommentMention(
              subjectType: 'user',
              subjectId: 'persona-2',
              displayName: '小李',
            ),
          ],
          personaContextVersion: 7,
        ),
      );

      expect(payload.pathParameters, <String, String>{'postId': 'post-1'});
      expect(payload.body, <String, Object?>{
        'content': '端云对象闭环',
        'replyToCommentId': 'comment-root',
        'attachmentMediaIds': <String>['asset-1'],
        'mentions': <Object?>[
          <String, Object?>{
            'subjectType': 'user',
            'subjectId': 'persona-2',
            'displayName': '小李',
          },
        ],
        'personaContextVersion': 7,
      });
    });

    test('创建评论 operation 声明频控的结构化恢复语义', () {
      final operation =
          appCloudOperationContracts[AppCloudOperationIds
              .contentCommentCreateComment];

      expect(operation, isNotNull);
      expect(
        operation!.errorCodes,
        contains(ContentErrorCode.commentRateLimited.code),
      );
      expect(ContentErrorCode.commentRateLimited.httpStatus, 429);
      expect(ContentErrorCode.commentRateLimited.recoveryAction, 'retry');
    });
  });
}

Map<String, Object?> _wireItem({
  required String id,
  List<Object?> attachments = const <Object?>[],
  List<Object?> replies = const <Object?>[],
}) {
  return <String, Object?>{
    'id': id,
    'version': 3,
    'postId': 'post-1',
    'authorId': 'persona-1',
    'authorDisplayNameSnapshot': '张三',
    'authorAvatarUrlSnapshot': 'https://cdn.example.com/avatar.jpg',
    'personaContextVersion': 7,
    'content': '商用评论',
    'replyToCommentId': null,
    'replyToUserId': null,
    'parentCommentId': null,
    'attachmentMediaIds': <String>['asset-1'],
    'attachments': attachments,
    'mentions': <Object?>[],
    'assistantMentioned': false,
    'assistantReplySource': null,
    'assistantCorrectionStatus': null,
    'status': 'active',
    'isPinned': true,
    'pinnedAt': '2026-07-14T08:01:00Z',
    'createdAt': '2026-07-14T08:00:00Z',
    'updatedAt': '2026-07-14T08:01:00Z',
    'deletedAt': null,
    'replyCount': replies.length,
    'replyPreview': replies,
    'replyNextCursor': null,
    'likeCount': 12,
    'dislikeCount': 2,
    'viewerReaction': 'like',
    'authorLiked': true,
    'viewerRelation': 'following',
    'isAuthor': true,
    'canDelete': true,
    'canReply': true,
    'canReport': false,
    'canPin': true,
  };
}
