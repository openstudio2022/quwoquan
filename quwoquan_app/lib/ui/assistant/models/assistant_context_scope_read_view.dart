/// 只读投影：收窄对会话 `contextScope` Map 的散列访问。
class AssistantContextScopeReadView {
  AssistantContextScopeReadView(this.raw);

  final Map<String, dynamic> raw;

  Map<String, dynamic> get privacyPolicy =>
      (raw['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  List<String> get normalizedUserTags =>
      (raw['userTags'] as List?)
          ?.whereType<String>()
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false) ??
      const <String>[];

  String get pageType => (raw['pageType'] as String?) ?? 'chat';
}
