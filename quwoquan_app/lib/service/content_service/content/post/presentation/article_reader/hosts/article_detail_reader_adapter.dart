import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/hosts/article_reader_host_adapter.dart';

class ArticleDetailReaderAdapter extends ArticleReaderHostAdapter {
  const ArticleDetailReaderAdapter(this.config);

  final ArticleReaderHostConfig config;

  @override
  ArticleReaderHostConfig resolveReaderConfig(BuildContext context) => config;
}
