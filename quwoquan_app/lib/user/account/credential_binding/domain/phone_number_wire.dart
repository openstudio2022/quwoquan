/// 返回可供大陆手机号 UI 展示的 11 位本地号码；无效输入返回空串。
String mainlandPhoneLocalDigitsOrEmpty(String value) {
  final digits = value.replaceAll(RegExp(r'\D'), '');
  final localDigits = digits.length == 13 && digits.startsWith('86')
      ? digits.substring(2)
      : digits;
  return RegExp(r'^1[3-9]\d{9}$').hasMatch(localDigits) ? localDigits : '';
}

/// 判断输入能否收敛为合法的大陆手机号。
bool isValidMainlandPhoneNumber(String value) =>
    mainlandPhoneLocalDigitsOrEmpty(value).isNotEmpty;

/// 在 App -> Cloud command 边界一次性收敛为 E.164；无效输入返回空串。
String mainlandPhoneE164OrEmpty(String value) {
  final localDigits = mainlandPhoneLocalDigitsOrEmpty(value);
  return localDigits.isEmpty ? '' : '+86$localDigits';
}
