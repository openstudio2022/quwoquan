import 'dart:convert';

import 'package:crypto/crypto.dart';

/// 通讯录手机号规范化 + 哈希（端云唯一真相源的端侧镜像）。
///
/// 必须与服务端 `services/user-service/internal/user/account/user_account/domain/user/phonematch` 逐字符等价：
/// 同一个真实手机号在端云派生出相同 hash，匹配只在哈希域完成，手机号原文不出库、不上行。
/// `salt` 是应用级稳定命名常量（随客户端分发，非密钥），端云只保留同一个值。
/// 一致性由两端共享测试向量锁定（见 contact_hash_service__local_contract_test.dart 与
/// phonematch__local_contract_test.go）。
class ContactHashService {
  const ContactHashService();

  static const String salt = 'qwq.contact';

  /// 规范化为 E.164-ish 形态：CN 11 位手机(以 1 开头)补 +86；已带 + 或国家码的保留为
  /// `+{digits}`。与 Go `phonematch.Canonicalize` 对齐。空输入返回空串。
  String canonicalize(String phone) {
    final trimmed = phone.trim();
    if (trimmed.isEmpty) {
      return '';
    }
    final hasPlus = trimmed.startsWith('+');
    final digits = _onlyDigits(trimmed);
    if (digits.isEmpty) {
      return '';
    }
    if (hasPlus) {
      return '+$digits';
    }
    if (digits.length == 11 && digits.codeUnitAt(0) == 0x31 /* '1' */ ) {
      return '+86$digits';
    }
    if (digits.length == 13 && digits.startsWith('86')) {
      return '+$digits';
    }
    if (digits.length == 14 && digits.startsWith('086')) {
      return '+${digits.substring(1)}';
    }
    return '+$digits';
  }

  /// 返回 `hex(SHA256("{salt}:{canonical}"))`；空输入返回空串。与 Go `phonematch.Hash` 对齐。
  String hash(String phone) {
    final canon = canonicalize(phone);
    if (canon.isEmpty) {
      return '';
    }
    final digest = sha256.convert(utf8.encode('$salt:$canon'));
    return digest.toString();
  }

  /// 批量派生：跳过空号，去重保持稳定顺序。
  List<String> hashAll(Iterable<String> phones) {
    final seen = <String>{};
    final out = <String>[];
    for (final phone in phones) {
      final h = hash(phone);
      if (h.isNotEmpty && seen.add(h)) {
        out.add(h);
      }
    }
    return out;
  }

  String _onlyDigits(String s) {
    final buffer = StringBuffer();
    for (final unit in s.codeUnits) {
      if (unit >= 0x30 && unit <= 0x39) {
        buffer.writeCharCode(unit);
      }
    }
    return buffer.toString();
  }
}
