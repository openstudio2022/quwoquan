import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_catalog.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_page.dart';

/// Composition-boundary factory for embedding the Filter Catalog editor from
/// Post and Media Upload presentation flows.
Widget buildImageEditorPage({
  Key? key,
  required String initialPath,
  required String source,
  int index = 0,
  int total = 1,
  List<String>? imagePaths,
  String? initialFilterPresetId,
  double? initialFilterStrength,
  ImageEditorFilterCatalog? filterRepository,
  VoidCallback? onBack,
  ValueChanged<Object?>? onDone,
}) {
  return ImageEditorPage(
    key: key,
    initialPath: initialPath,
    source: source,
    index: index,
    total: total,
    imagePaths: imagePaths,
    initialFilterPresetId: initialFilterPresetId,
    initialFilterStrength: initialFilterStrength,
    filterRepository: filterRepository,
    onBack: onBack,
    onDone: onDone,
  );
}
