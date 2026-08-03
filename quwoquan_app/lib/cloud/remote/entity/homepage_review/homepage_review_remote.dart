import 'package:quwoquan_app/application/entity/homepage_review_operation_ports.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef HomepageReviewInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// Production-only adapter. It contains no paths, operation IDs, JSON maps,
/// actor headers, decoders or fallback behavior.
final class RemoteHomepageReviewFacet
    implements HomepageReviewCommandWriter, HomepageReviewQuery {
  const RemoteHomepageReviewFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageReviewInvocationContextFactory invocationContext;

  @override
  Future<HomepageReviewView> create(CreateHomepageReviewCommand command) =>
      client.entityHomepageReviewCreateHomepageReview(
        command,
        context: invocationContext(
          EntityRequestPageIds.createHomepageReview,
          command: true,
        ),
      );

  @override
  Future<HomepageReviewView> update(UpdateHomepageReviewCommand command) =>
      client.entityHomepageReviewUpdateHomepageReview(
        command,
        context: invocationContext(
          EntityRequestPageIds.updateHomepageReview,
          command: true,
        ),
      );

  @override
  Future<HomepageReviewView> delete(DeleteHomepageReviewCommand command) =>
      client.entityHomepageReviewDeleteHomepageReview(
        command,
        context: invocationContext(
          EntityRequestPageIds.deleteHomepageReview,
          command: true,
        ),
      );

  @override
  Future<HomepageReviewPageSlice> listByHomepage(
    HomepageReviewListQuery query,
  ) => client.entityHomepageReviewListHomepageReviews(
    query,
    context: invocationContext(
      EntityRequestPageIds.listHomepageReviews,
      command: false,
    ),
  );

  @override
  Future<HomepageReviewView> getMine(MyHomepageReviewQuery query) =>
      client.entityHomepageReviewGetMyHomepageReview(
        query,
        context: invocationContext(
          EntityRequestPageIds.getMyHomepageReview,
          command: false,
        ),
      );
}
