// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/home_channels_remote_override.dart';

void main() {
  group('HomeChannelsRemoteOverride.fromAppConfigRoot', () {
    test('解析 content.home_channels 运营覆盖（snake_case）并按 order 升序', () {
      final root = <String, Object?>{
        'content': <String, Object?>{
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
        },
      };

      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(root);

      expect(channels, isNotNull);
      expect(channels!.map((c) => c.id).toList(), <String>[
        'following',
        'recommend',
      ]);
      final recommend = channels.firstWhere((c) => c.id == 'recommend');
      expect(recommend.template, 'intersection_rail_masonry');
      expect(recommend.feedQuery['category'], 'micro');
      expect(recommend.feedQuery['identity'], 'moment');
      expect(recommend.moodCopyKey, 'home_mood_recommend');
    });

    test('缺失 home_channels → null（回退端默认）', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{'feature_flags': <String, Object?>{}},
        },
      );
      expect(channels, isNull);
    });

    test('空列表 → null（回退端默认）', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{'home_channels': <Object?>[]},
        },
      );
      expect(channels, isNull);
    });

    test('任一缺 id 或非 Map 条目使整份覆盖回退', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'home_channels': <Object?>[
              <String, Object?>{'label_key': 'x', 'order': 0},
              'not-a-map',
            ],
          },
        },
      );
      expect(channels, isNull);
    });

    test('合法与非法条目混合时禁止部分接受', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'home_channels': <Object?>[
              <String, Object?>{
                'id': 'recommend',
                'feed_query': <String, Object?>{'channel': 'recommend'},
                'order': 0,
              },
              <String, Object?>{'label_key': 'missing-id', 'order': 1},
            ],
          },
        },
      );

      expect(channels, isNull);
    });

    test('存在非法 feed_query 类型或值时整份回退', () {
      for (final feedQuery in <Object?>[
        'recommend',
        <String, Object?>{'channel': 42},
      ]) {
        final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
          <String, Object?>{
            'content': <String, Object?>{
              'home_channels': <Object?>[
                <String, Object?>{
                  'id': 'recommend',
                  'feed_query': feedQuery,
                  'order': 0,
                },
              ],
            },
          },
        );

        expect(channels, isNull, reason: 'feed_query=$feedQuery');
      }
    });

    test('字段类型不符合 canonical schema 时整份回退', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'home_channels': <Object?>[
              <String, Object?>{
                'id': 'recommend',
                'supports_full_span_modules': 'false',
                'order': '0',
              },
            ],
          },
        },
      );

      expect(channels, isNull);
    });

    test('最多接受 8 个唯一频道；超过上限整份回退端默认', () {
      expect(HomeChannelsRemoteOverride.maximumChannelCount, 8);
      final maximumChannels = List<Object?>.generate(
        HomeChannelsRemoteOverride.maximumChannelCount,
        (index) => <String, Object?>{'id': 'channel-$index', 'order': index},
      );

      final accepted = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{'home_channels': maximumChannels},
        },
      );
      final rejected = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'home_channels': <Object?>[
              ...maximumChannels,
              <String, Object?>{'id': 'channel-overflow', 'order': 8},
            ],
          },
        },
      );

      expect(accepted, hasLength(8));
      expect(rejected, isNull);
    });

    test('有效频道 id 必须唯一；重复时整份回退端默认', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'home_channels': <Object?>[
              <String, Object?>{'id': 'recommend', 'order': 0},
              <String, Object?>{'id': ' recommend ', 'order': 1},
            ],
          },
        },
      );

      expect(channels, isNull);
    });

    test('camelCase 字段不再兼容，返回 null', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'content': <String, Object?>{
            'homeChannels': <Object?>[
              <String, Object?>{
                'id': 'campus',
                'labelKey': 'home_tab_campus',
                'template': 'intersection_rail_masonry',
                'feedQuery': <String, Object?>{'category': 'campus'},
                'moodCopyKey': 'home_mood_campus',
                'order': 0,
              },
            ],
          },
        },
      );
      expect(channels, isNull);
    });

    test('根级 home_channels 不再作为第二条读取路径', () {
      final channels = HomeChannelsRemoteOverride.fromAppConfigRoot(
        <String, Object?>{
          'home_channels': <Object?>[
            <String, Object?>{'id': 'retired-root-shape', 'order': 0},
          ],
        },
      );

      expect(channels, isNull);
    });
  });
}
