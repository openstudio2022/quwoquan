import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/article_reader_host_adapter.dart';

class ArticleDetailReaderAdapter extends ArticleReaderHostAdapter {
  const ArticleDetailReaderAdapter(this.config);

  final ArticleReaderHostConfig config;

  @override
  ArticleReaderHostConfig resolveReaderConfig(BuildContext context) => config;
}
