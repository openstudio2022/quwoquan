import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';

extension ChatGroupSettingsDtoPatch on ChatGroupSettingsDto {
  /// 群名编辑权限 PATCH 体；只发送 metadata 声明的可写字段。
  Map<String, dynamic> toGroupSettingsPatchBody() => <String, dynamic>{
    'nameEditableByAdminOnly': nameEditableByAdminOnly,
  };
}
