// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/home_channels_remote_override.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentAppConfig _config(Map<String, Object?> fields) {
  return ContentAppConfig.fromWire(<String, Object?>{
    'feature_flags': const <String, Object?>{},
    'gray_release': const <String, Object?>{
      'experiment_bucket': 'control',
      'current_stage': 'control',
      'canary_matrix': <Object?>[],
    },
    ...fields,
  });
}

void main() {
  group('HomeChannelsRemoteOverride.fromAppConfig', () {
    test('解析 generated homeChannels 并按 order 升序', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfig(
        _config(<String, Object?>{
          'home_channels': <Object?>[
            <String, Object?>{
              'id': 'recommend',
              'label_key': 'home_tab_recommend',
              'template': 'intersection_rail_masonry',
              'feed_query': <String, Object?>{
                'category': 'micro',
                'identity': 'moment',
              },
              'mood_copy_key': 'home_mood_recommend',
              'order': 1,
            },
            <String, Object?>{
              'id': 'following',
              'label_key': 'home_tab_following',
              'template': 'single_column_relations',
              'feed_query': <String, Object?>{'category': 'following'},
              'mood_copy_key': 'home_mood_following',
              'order': 0,
            },
          ],
        }),
      );

      expect(channels!.map((channel) => channel.id), <String>[
        'following',
        'recommend',
      ]);
      final recommend = channels.last;
      expect(recommend.template, 'intersection_rail_masonry');
      expect(recommend.feedQuery, <String, String>{
        'category': 'micro',
        'identity': 'moment',
      });
    });

    test('缺失或空 homeChannels 时回退端默认', () {
      expect(
        HomeChannelsRemoteOverride.fromAppConfig(_config(const {})),
        isNull,
      );
      expect(
        HomeChannelsRemoteOverride.fromAppConfig(
          _config(const <String, Object?>{'home_channels': <Object?>[]}),
        ),
        isNull,
      );
    });

    test('feedQuery 非字符串值时整份回退', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfig(
        _config(<String, Object?>{
          'home_channels': <Object?>[
            <String, Object?>{
              'id': 'recommend',
              'feed_query': <String, Object?>{'channel': 42},
              'order': 0,
            },
          ],
        }),
      );
      expect(channels, isNull);
    });

    test('最多接受 8 个唯一频道', () {
      final maximumChannels = List<Object?>.generate(
        HomeChannelsRemoteOverride.maximumChannelCount,
        (index) => <String, Object?>{'id': 'channel-$index', 'order': index},
      );
      expect(
        HomeChannelsRemoteOverride.fromAppConfig(
          _config(<String, Object?>{'home_channels': maximumChannels}),
        ),
        hasLength(8),
      );
      expect(
        HomeChannelsRemoteOverride.fromAppConfig(
          _config(<String, Object?>{
            'home_channels': <Object?>[
              ...maximumChannels,
              <String, Object?>{'id': 'overflow', 'order': 8},
            ],
          }),
        ),
        isNull,
      );
    });

    test('频道 id 规范化后必须唯一', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfig(
        _config(<String, Object?>{
          'home_channels': const <Object?>[
            <String, Object?>{'id': 'recommend', 'order': 0},
            <String, Object?>{'id': ' recommend ', 'order': 1},
          ],
        }),
      );
      expect(channels, isNull);
    });

    test('generated decoder 拒绝 camelCase 与非法字段类型', () {
      expect(
        () => _config(const <String, Object?>{'homeChannels': <Object?>[]}),
        throwsFormatException,
      );
      expect(
        () => _config(const <String, Object?>{
          'home_channels': <Object?>[
            <String, Object?>{
              'id': 'recommend',
              'supports_full_span_modules': 'false',
            },
          ],
        }),
        throwsFormatException,
      );
    });
  });
}
