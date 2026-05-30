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
                'category': 'moment',
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
      expect(recommend.feedQuery['category'], 'moment');
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

    test('跳过缺 id 的非法条目；全非法 → null', () {
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

    test('camelCase 字段兼容', () {
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
      expect(channels, isNotNull);
      expect(channels!.single.id, 'campus');
      expect(channels.single.labelKey, 'home_tab_campus');
      expect(channels.single.feedQuery['category'], 'campus');
    });
  });
}
