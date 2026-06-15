class SettingsCommercialAccountText {
  const SettingsCommercialAccountText._();

  static const String sectionTitle = '账号安全与隐私';
  static const String credentials = '登录方式与凭证';
  static const String credentialsReady = '已接入';
  static const String credentialsMessage =
      '已具备凭证列表、绑定与解绑的端云接口；上线前还需补完整页面、最后一个凭证保护提示与冲突处理。';
  static const String devices = '登录设备与会话';
  static const String devicesBlocked = '上线阻断';
  static const String devicesMessage =
      '最近设备、会话审计、退出当前设备/全部设备还没有前台闭环，商用上线前必须补 UI、SLO 与告警。';
  static const String delete = '账号注销与恢复';
  static const String deleteBlocked = '上线阻断';
  static const String deleteMessage =
      '账号注销、恢复申诉、锁定态解释与客服 handoff 仍是 P0 阻断，不能以“待接入”进入 release。';
  static const String dataRights = '数据导出与撤回同意';
  static const String dataRightsBlocked = '上线阻断';
  static const String dataRightsMessage =
      '数据导出、撤回同意、隐私设置留痕与法律文本版本需要形成可审计闭环后才可上线。';
  static const String loginRequired = '登录后管理账号安全';
}
