import "package:quwoquan_app/cloud/services/chat/chat_view_data.dart";

extension ChatGroupSettingsDtoPatch on ChatGroupSettingsViewData {
  /// 群名编辑权限 PATCH 体；只发送 metadata 声明的可写字段。
  Map<String, dynamic> toGroupSettingsPatchBody() => <String, dynamic>{
    'nameEditableByAdminOnly': nameEditableByAdminOnly,
  };
}
