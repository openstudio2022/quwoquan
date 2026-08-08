import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_remote_config.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentAppConfig _config(Map<String, Object?> comment) {
  return ContentAppConfig.fromWire(<String, Object?>{
    'feature_flags': const <String, Object?>{},
    'gray_release': const <String, Object?>{
      'experiment_bucket': 'control',
      'current_stage': 'control',
      'canary_matrix': <Object?>[],
    },
    'comment': comment,
  });
}

void main() {
  group('CommentRemoteConfig.fromAppConfig', () {
    test('把 generated comment 投影为端侧运行时配置', () {
      final config = CommentRemoteConfig.fromAppConfig(
        _config(const <String, Object?>{
          'max_length': 320,
          'reply_preview_count': 2,
          'reply_first_expand_page_size': 6,
          'reply_expand_page_size': 12,
          'fold_line_count': 4,
          'attachment': <String, Object?>{'max_images': 3},
        }),
      );

      expect(config.maxLength, 320);
      expect(config.replyPreviewCount, 2);
      expect(config.replyFirstExpandPageSize, 6);
      expect(config.replyExpandPageSize, 12);
      expect(config.foldLineCount, 4);
      expect(config.maxImageAttachments, 3);
    });

    test('缺失字段沿用端侧 fallback', () {
      final config = CommentRemoteConfig.fromAppConfig(
        _config(const <String, Object?>{}),
        fallback: const CommentRemoteConfig(
          maxLength: 500,
          maxImageAttachments: 2,
          enabled: true,
        ),
      );

      expect(config.maxLength, 500);
      expect(config.maxImageAttachments, 2);
      expect(config.enabled, isTrue);
    });

    test('generated decoder 拒绝旧字段和字符串化 scalar', () {
      expect(
        () => _config(const <String, Object?>{'attachment_max_count': 9}),
        throwsFormatException,
      );
      expect(
        () => _config(const <String, Object?>{
          'max_length': '320',
          'enabled': 'false',
        }),
        throwsFormatException,
      );
    });
  });
}
