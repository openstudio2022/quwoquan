import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/src/scene/pageflip_book_scene_contract.dart';

@immutable
class PageflipBookTextureSessionContract {
  const PageflipBookTextureSessionContract({
    required this.binding,
    this.sheetBinding,
    required this.preferHighFidelity,
    this.hasResolvedBundle = false,
    this.hasMatchingBinding = true,
  });

  final PageflipBookSurfaceRoleBinding binding;
  final PageflipBookSheetBinding? sheetBinding;
  final bool preferHighFidelity;
  final bool hasResolvedBundle;
  final bool hasMatchingBinding;

  List<int> get prioritizedPageIndices =>
      sheetBinding?.prioritizedPageIndices ?? binding.prioritizedPageIndices;

  Set<int> get requiredPageIndices =>
      sheetBinding?.requiredPageIndices ?? binding.requiredPageIndices;

  bool get hasCanonicalSheetBinding => sheetBinding != null;

  bool get isReadyForHighFidelity =>
      preferHighFidelity && hasResolvedBundle && hasMatchingBinding;

  PageflipBookTextureSessionContract copyWith({
    PageflipBookSurfaceRoleBinding? binding,
    PageflipBookSheetBinding? sheetBinding,
    bool? preferHighFidelity,
    bool? hasResolvedBundle,
    bool? hasMatchingBinding,
  }) {
    return PageflipBookTextureSessionContract(
      binding: binding ?? this.binding,
      sheetBinding: sheetBinding ?? this.sheetBinding,
      preferHighFidelity: preferHighFidelity ?? this.preferHighFidelity,
      hasResolvedBundle: hasResolvedBundle ?? this.hasResolvedBundle,
      hasMatchingBinding: hasMatchingBinding ?? this.hasMatchingBinding,
    );
  }
}
