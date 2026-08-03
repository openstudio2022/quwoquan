// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_setup_schema.dart';

void main() {
  test('parses the safe setup schema subset without guessing fields', () {
    final schema = AssistantSkillSetupSchema.tryParse(<String, Object?>{
      'type': 'object',
      'additionalProperties': false,
      'required': <String>['pace'],
      'properties': <String, Object?>{
        'pace': <String, Object?>{
          'type': 'string',
          'title': '旅行节奏',
          'enum': <String>['relaxed', 'balanced'],
          'x-enum-labels': <String, String>{'relaxed': '轻松', 'balanced': '均衡'},
        },
        'lead': <String, Object?>{
          'type': 'integer',
          'title': '提前提醒',
          'minimum': 5,
          'maximum': 60,
        },
        'food': <String, Object?>{
          'type': 'array',
          'items': <String, String>{'type': 'string'},
          'maxItems': 3,
        },
      },
    });

    expect(schema, isNotNull);
    expect(schema!.fields, hasLength(3));
    expect(schema.fields.first.required, isTrue);
    expect(schema.fields.first.labelFor('relaxed'), '轻松');
    expect(schema.fields[1].validate(4), isNotNull);
    expect(schema.fields[1].validate(30), isNull);
    expect(schema.fields[2].validate(<String>['a', 'b', 'c', 'd']), isNotNull);
  });

  test('fails closed for extensible or unsupported schemas', () {
    expect(
      AssistantSkillSetupSchema.tryParse(<String, Object?>{
        'type': 'object',
        'additionalProperties': true,
        'properties': <String, Object?>{},
      }),
      isNull,
    );
    expect(
      AssistantSkillSetupSchema.tryParse(<String, Object?>{
        'type': 'object',
        'additionalProperties': false,
        'properties': <String, Object?>{
          'unsafe': <String, String>{'type': 'object'},
        },
      }),
      isNull,
    );
  });
}
