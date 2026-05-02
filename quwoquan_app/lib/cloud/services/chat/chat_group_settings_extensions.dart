import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';

extension ChatGroupSettingsDtoPatch on ChatGroupSettingsDto {
  /// 群管理开关 PATCH 体（与 Mock/记录 wire 键一致）。
  Map<String, dynamic> toGroupSettingsPatchBody() => <String, dynamic>{
    'qrCodeJoinEnabled': qrCodeJoinEnabled,
    'joinRequiresApproval': joinRequiresApproval,
    'nameEditableByAdminOnly': nameEditableByAdminOnly,
    'privacyShieldAdminOnly': privacyShieldAdminOnly,
  };
}
