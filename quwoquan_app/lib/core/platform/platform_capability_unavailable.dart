import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// Thrown by anti-corruption gateways when a capability is not available on the
/// current platform. Exposes a structured [RuntimeFailure] so UI/provider error
/// surfaces can render a consistent, cross-platform degradation message rather
/// than a raw exception string, as required by the App runtime error contract.
class PlatformCapabilityUnavailableException implements Exception {
  PlatformCapabilityUnavailableException({
    required this.capability,
    this.detail = '',
  });

  /// Capability key (e.g. `hasLocalFileSystem`, `nativeVideoEditing`).
  final String capability;

  /// Optional non-user-facing diagnostic detail.
  final String detail;

  RuntimeFailure get runtimeFailure =>
      RuntimeFailure.unknown(code: 'CLIENT.PLATFORM.capability_unavailable');

  @override
  String toString() =>
      'PlatformCapabilityUnavailableException(capability: $capability'
      '${detail.isEmpty ? '' : ', detail: $detail'})';
}
