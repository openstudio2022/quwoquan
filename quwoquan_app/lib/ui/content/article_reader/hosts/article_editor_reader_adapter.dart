import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/article_reader_host_adapter.dart';

/// Adapter reserved for editor preview hosts.
///
/// Editor-specific concerns such as draft refresh, selection state, and
/// in-progress media placeholders should terminate here instead of leaking into
/// flip pipelines.
class ArticleEditorReaderAdapter extends ArticleReaderHostAdapter {
  const ArticleEditorReaderAdapter(this.config);

  final ArticleReaderHostConfig config;

  @override
  ArticleReaderHostConfig resolveReaderConfig(BuildContext context) => config;
}
