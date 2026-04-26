import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

enum AssistantDeviceProfile {
  mobile,
  tablet,
  pc,
}

enum AssistantCapabilityMode {
  localOnly,
  remotePreferred,
  hybrid,
}

class AssistantCapabilityDecision {
  const AssistantCapabilityDecision({
    required this.mode,
    required this.reason,
  });

  final AssistantCapabilityMode mode;
  final String reason;
}

class AssistantCapabilityRouter {
  const AssistantCapabilityRouter();

  AssistantCapabilityDecision decide({
    required String deviceProfile,
    required String capabilityName,
  }) {
    final profile = _parseProfile(deviceProfile);

    if (profile == AssistantDeviceProfile.mobile &&
        AssistantToolNames.isRetrievalName(capabilityName)) {
      return const AssistantCapabilityDecision(
        mode: AssistantCapabilityMode.hybrid,
        reason: 'mobile web capability prefers hybrid fallback',
      );
    }

    final normalized = capabilityName.trim().toLowerCase();
    if (profile == AssistantDeviceProfile.pc &&
        normalized.contains('gallery')) {
      return const AssistantCapabilityDecision(
        mode: AssistantCapabilityMode.remotePreferred,
        reason: 'pc can forward heavy or privileged tasks to remote node',
      );
    }

    if (profile == AssistantDeviceProfile.tablet &&
        normalized.contains('intent')) {
      return const AssistantCapabilityDecision(
        mode: AssistantCapabilityMode.hybrid,
        reason: 'tablet intent uses hybrid due to platform variance',
      );
    }

    return const AssistantCapabilityDecision(
      mode: AssistantCapabilityMode.localOnly,
      reason: 'default local execution',
    );
  }

  AssistantDeviceProfile _parseProfile(String raw) {
    switch (raw.trim().toLowerCase()) {
      case 'tablet':
        return AssistantDeviceProfile.tablet;
      case 'pc':
      case 'desktop':
        return AssistantDeviceProfile.pc;
      case 'mobile':
      default:
        return AssistantDeviceProfile.mobile;
    }
  }
}
