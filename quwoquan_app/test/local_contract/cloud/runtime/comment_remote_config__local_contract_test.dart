import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';

void main() {
  group('CommentRemoteConfig.fromAppConfigRoot', () {
    test('解析 comment.attachment.max_images 的 canonical 蛇形键', () {
      final config = CommentRemoteConfig.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'comment': <String, Object?>{
              'max_length': 320,
              'reply_preview_count': 2,
              'reply_first_expand_page_size': 6,
              'reply_expand_page_size': 12,
              'fold_line_count': 4,
              'attachment': <String, Object?>{'max_images': 3},
            },
          },
        },
      );

      expect(config.maxLength, 320);
      expect(config.replyPreviewCount, 2);
      expect(config.replyFirstExpandPageSize, 6);
      expect(config.replyExpandPageSize, 12);
      expect(config.foldLineCount, 4);
      expect(config.maxImageAttachments, 3);
    });

    test('attachment_max_count 旧字段不再生效', () {
      final config = CommentRemoteConfig.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'comment': <String, Object?>{
              'attachment_max_count': 9,
            },
          },
        },
        fallback: const CommentRemoteConfig(maxImageAttachments: 2),
      );

      expect(config.maxImageAttachments, 2);
    });
  });
}
