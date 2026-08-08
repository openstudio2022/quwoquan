// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
//
// `AssistantUsePolicy` 的 canonical 取值只有 `inherit` / `exclude`
// （`quwoquan_service/contracts/metadata/_shared/types.yaml#enums`）。
// 本套件证明端侧已经从裸 String 改为 typed enum，且非法取值在**解码阶段**
// 就被结构化拒绝，而不是静默穿过 decoder 继续在 App 内流转。
//
// 负例优先：先证明 `allow` / `allow_summary` / `excluded` 这类历史漂移值会被拒绝，
// 再证明 canonical 取值仍然可以正常往返。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/assistant_use_policy_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/qwq_markdown_ast.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 历史上真实出现在测试树与服务 fixture 里的非法取值。
const List<String> _retiredIllegalPolicies = <String>[
  'allow',
  'allow_summary',
  'excluded',
];

/// 从 wire map 解码 projection。
///
/// 契约层已经把 `assistantUsePolicy` 收成 typed enum，非法取值只可能在 wire 解码
/// 这一个点上出现，所以负例必须从 map 进入，而不是从构造函数进入。
ContentPostProjection _projection(String? assistantUsePolicy) =>
    ContentPostProjection.fromWire(<String, Object?>{
      'postId': 'post-assistant-policy',
      'contentType': 'micro',
      'contentIdentity': 'moment',
      'assistantUsePolicy': ?assistantUsePolicy,
      'authorId': 'author-assistant-policy',
      'authorDisplayName': '策略作者',
      'authorAvatarUrl': '',
      'likeCount': 0,
      'commentCount': 0,
      'shareCount': 0,
      'createdAt': '2026-08-07T00:00:00.000Z',
    });

void main() {
  group('AssistantUsePolicy 解码拒绝非法取值', () {
    test('canonical 枚举只承认 inherit 与 exclude', () {
      expect(
        AssistantUsePolicy.values.map((value) => value.wireName).toList(),
        <String>['inherit', 'exclude'],
      );
    });

    for (final illegal in _retiredIllegalPolicies) {
      test('ContentPostViewData.fromWire 拒绝 $illegal', () {
        expect(
          () => ContentPostViewData.fromWire(_projection(illegal)),
          throwsA(isA<FormatException>()),
        );
      });

      test('PublishSettings.fromMap 拒绝草稿里的 $illegal', () {
        expect(
          () => PublishSettings.fromMap(<String, dynamic>{
            'assistantUsePolicy': illegal,
          }),
          throwsA(isA<FormatException>()),
        );
      });

      test('QwqMarkdownFrontMatter.fromMap 拒绝 front matter 里的 $illegal', () {
        expect(
          () => QwqMarkdownFrontMatter.fromMap(<String, Object?>{
            'assistantUsePolicy': illegal,
          }),
          throwsA(isA<FormatException>()),
        );
      });
    }

    test('非法取值映射为 APP.CONTRACT.invalid_json，动态上下文不进 code', () {
      Object? captured;
      try {
        ContentPostViewData.fromWire(_projection('allow'));
      } catch (error) {
        captured = error;
      }
      expect(captured, isA<FormatException>());

      final failure = CloudErrorMapper.runtimeFailureFromException(
        captured!,
        requestPath: '/content/posts',
      );
      expect(failure.code, RuntimeFailureCodes.appContractInvalidJson);
      expect(failure.code.split('.'), hasLength(3));
      for (final attribute in failure.context.attributes) {
        expect(attribute.value, isA<String>());
      }
    });
  });

  group('AssistantUsePolicy typed 往返', () {
    test('缺省时落到契约默认值 inherit', () {
      expect(
        ContentPostViewData.fromWire(_projection(null)).assistantUsePolicy,
        AssistantUsePolicy.inherit,
      );
      expect(
        assistantUsePolicyFromWire(null, 'test'),
        AssistantUsePolicy.inherit,
      );
      expect(assistantUsePolicyFromWire('', 'test'), AssistantUsePolicy.inherit);
    });

    test('exclude 在 ViewData 与 payload 之间保持 typed 往返', () {
      expect(
        ContentPostViewData.fromWire(_projection('exclude')).assistantUsePolicy,
        AssistantUsePolicy.exclude,
      );
      const settings = PublishSettings(
        assistantUsePolicy: AssistantUsePolicy.exclude,
      );
      expect(settings.toPayloadFields()['assistantUsePolicy'], 'exclude');
      expect(
        PublishSettings.fromMap(settings.toMap()).assistantUsePolicy,
        AssistantUsePolicy.exclude,
      );
    });

    test('front matter 未声明该键时保持未声明，不伪造默认值', () {
      expect(
        QwqMarkdownFrontMatter.fromMap(const <String, Object?>{}).assistantUsePolicy,
        isNull,
      );
      expect(
        QwqMarkdownFrontMatter.fromMap(const <String, Object?>{
          'assistantUsePolicy': 'exclude',
        }).toMap()['assistantUsePolicy'],
        'exclude',
      );
    });
  });
}
