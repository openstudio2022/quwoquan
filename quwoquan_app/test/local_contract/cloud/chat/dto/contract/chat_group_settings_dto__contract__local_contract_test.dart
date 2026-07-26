// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_group_settings_extensions.dart';

void main() {
  test('ChatGroupSettingsDto 与 PATCH 只保留权威治理字段', () {
    final settings = ChatGroupSettingsDto(
      nameEditableByAdminOnly: true,
      conversationType: 'group',
      circleId: 'circle_contract',
    );

    expect(settings.toMap(), <String, dynamic>{
      'nameEditableByAdminOnly': true,
      'conversationType': 'group',
      'circleId': 'circle_contract',
      'circleGroupId': '',
    });
    expect(settings.toGroupSettingsPatchBody(), <String, dynamic>{
      'nameEditableByAdminOnly': true,
    });
  });
}
