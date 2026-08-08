import 'package:quwoquan_app/service/tag_service/tag/tag_feedback_fact/adapters/tag_feedback_fact_remote.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_feedback_fact/application/tag_feedback_fact_appender.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/adapters/tag_catalog_remote.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// tag domain 的唯一 production 装配入口。
final class TagProductionComposition {
  const TagProductionComposition._();

  static TagCatalogQuery catalogQuery({
    required GeneratedCloudOperationClient client,
    required TagCatalogInvocationContextFactory invocationContext,
  }) {
    return RemoteGeneratedTagCatalogQuery(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TagFeedbackFactAppender feedbackFactAppender({
    required GeneratedCloudOperationClient client,
    required TagInvocationContextFactory invocationContext,
  }) {
    return RemoteTagFeedbackAdapter(
      client: client,
      invocationContext: invocationContext,
    );
  }
}
