import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/article_reader_host_adapter.dart';

/// Adapter reserved for immersive browser reading surfaces.
///
/// Browser chrome, external navigation, and gesture arbitration belong in this
/// adapter layer, not in the shared flip host or direction pipelines.
class ImmersiveBrowserReaderAdapter extends ArticleReaderHostAdapter {
  const ImmersiveBrowserReaderAdapter(this.config);

  final ArticleReaderHostConfig config;

  @override
  ArticleReaderHostConfig resolveReaderConfig(BuildContext context) => config;
}
