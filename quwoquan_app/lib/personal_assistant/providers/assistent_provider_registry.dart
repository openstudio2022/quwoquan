enum AssistentProviderType {
  llm,
  search,
  embedding,
  rerank,
  billing,
}

class AssistentProviderDescriptor {
  const AssistentProviderDescriptor({
    required this.id,
    required this.type,
    required this.version,
    required this.enabled,
    this.metadata = const <String, dynamic>{},
  });

  final String id;
  final AssistentProviderType type;
  final String version;
  final bool enabled;
  final Map<String, dynamic> metadata;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'id': id,
      'type': type.name,
      'version': version,
      'enabled': enabled,
      'metadata': metadata,
    };
  }
}

class AssistentProviderRegistry {
  final Map<String, AssistentProviderDescriptor> _providers =
      <String, AssistentProviderDescriptor>{};
  final Map<String, DateTime> _disabledUntil = <String, DateTime>{};

  void register(AssistentProviderDescriptor descriptor) {
    _providers[descriptor.id] = descriptor;
  }

  void disableTemporarily({
    required String providerId,
    required Duration duration,
  }) {
    final provider = _providers[providerId];
    if (provider == null) return;
    _disabledUntil[providerId] = DateTime.now().add(duration);
  }

  void clearTemporaryDisable(String providerId) {
    _disabledUntil.remove(providerId);
  }

  bool isTemporarilyDisabled(String providerId) {
    final until = _disabledUntil[providerId];
    if (until == null) return false;
    if (DateTime.now().isAfter(until)) {
      _disabledUntil.remove(providerId);
      return false;
    }
    return true;
  }

  List<AssistentProviderDescriptor> list({
    AssistentProviderType? type,
    bool? enabled,
  }) {
    final values = _providers.values.where((provider) {
      final typeOk = type == null || provider.type == type;
      final effectiveEnabled = provider.enabled && !isTemporarilyDisabled(provider.id);
      final enabledOk = enabled == null || effectiveEnabled == enabled;
      return typeOk && enabledOk;
    });
    return values.toList(growable: false);
  }

  List<Map<String, dynamic>> listWithRuntimeState({
    AssistentProviderType? type,
  }) {
    final providers = list(type: type);
    return providers
        .map((provider) {
          final disabled = isTemporarilyDisabled(provider.id);
          return <String, dynamic>{
            ...provider.toJson(),
            'effectiveEnabled': provider.enabled && !disabled,
            'temporarilyDisabled': disabled,
            'disabledUntil': _disabledUntil[provider.id]?.toIso8601String(),
          };
        })
        .toList(growable: false);
  }
}

