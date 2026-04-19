import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_state.dart';

@immutable
class PageflipTextureSession {
  const PageflipTextureSession({
    required this.roleState,
    required this.preferHighFidelity,
    this.hasResolvedBundle = false,
    this.hasMatchingBinding = true,
  });

  final PageflipRoleState roleState;
  final bool preferHighFidelity;
  final bool hasResolvedBundle;
  final bool hasMatchingBinding;

  List<int> get prioritizedPageIndices => roleState.prioritizedPageIndices;

  Set<int> get requiredPageIndices =>
      Set<int>.unmodifiable(roleState.prioritizedPageIndices);

  bool get isReadyForHighFidelity =>
      preferHighFidelity && hasResolvedBundle && hasMatchingBinding;
}
