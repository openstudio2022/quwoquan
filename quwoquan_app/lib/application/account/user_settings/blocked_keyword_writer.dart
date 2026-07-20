import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将“屏蔽此关键词”用户动作协调为 UserSettings Privacy typed command。
///
/// 不维护第二份本地关键词列表；每次以服务端 snapshot 为基线做集合追加，
/// 同值写由 UserSettings 聚合按 no-op 语义收敛。
final class BlockedKeywordWriter {
  const BlockedKeywordWriter({
    required this.query,
    required this.commands,
    this.onChanged,
  });

  final UserSettingsQueryReader query;
  final UserSettingsCommandWriter commands;
  final void Function(List<String> keywords)? onChanged;

  Future<void> add(String keyword) async {
    final normalized = keyword.trim();
    if (normalized.isEmpty) return;
    final current = await query.getPrivacySettings();
    final next = <String>{
      ...current.blockedKeywords.map((item) => item.trim()),
      normalized,
    }.where((item) => item.isNotEmpty).toList(growable: false);
    if (next.length == current.blockedKeywords.length) return;
    await commands.updatePrivacySettings(
      UpdatePrivacySettingsCommand(blockedKeywords: next),
    );
    onChanged?.call(next);
  }
}
