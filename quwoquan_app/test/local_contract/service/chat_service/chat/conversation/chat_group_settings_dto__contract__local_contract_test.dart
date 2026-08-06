// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/chat_group_settings_extensions.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';

void main() {
  test('ChatGroupSettingsViewData 与 PATCH 只保留权威治理字段', () {
    final settings = ChatGroupSettingsViewData(
      nameEditableByAdminOnly: true,
      conversationType: 'group',
      circleId: 'circle_contract',
    );

    expect(settings.nameEditableByAdminOnly, isTrue);
    expect(settings.conversationType, 'group');
    expect(settings.circleId, 'circle_contract');
    expect(settings.toGroupSettingsPatchBody(), <String, dynamic>{
      'nameEditableByAdminOnly': true,
    });
  });
}
