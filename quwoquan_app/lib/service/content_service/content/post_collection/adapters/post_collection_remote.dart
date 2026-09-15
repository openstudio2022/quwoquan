import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/post_collection.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/application/post_collection_port.dart';

final class RemotePostCollection implements PostCollectionPort {
  const RemotePostCollection({
    required this.client,
    required this.queries,
    required this.context,
  });
  final GeneratedCloudOperationClient client;
  final GeneratedPostCollectionGraphQLClient queries;
  final CloudOperationInvocationContext Function(String pageId, String? key)
  context;
  @override
  Future<PostCollectionManagementView> management(
    GetPostCollectionManagementQuery query,
  ) => queries.management(
    query,
    context: context(PageNames.postCollection, null),
  );
  @override
  Future<AuthorPostPageSlice> authorPosts(ContentAuthorPostsQuery query) =>
      client.contentPostListUserPosts(
        query,
        context: context(ContentRequestPageIds.listUserPosts, null),
      );
  @override
  Future<PostCollectionPage> get(GetPostCollectionQuery query) => queries.get(
    query,
    context: context(PageNames.postCollection, null),
  );
  @override
  Future<PostCollectionCommandResult> save(SavePostCollectionCommand command) =>
      client.contentPostCollectionSavePostCollection(
        command,
        context: context(
          ContentRequestPageIds.savePostCollection,
          'collection:${command.collectionId}:${command.expectedVersion}:save',
        ),
      );
  @override
  Future<PostCollectionCommandResult> delete(
    DeletePostCollectionCommand command,
  ) => client.contentPostCollectionDeletePostCollection(
    command,
    context: context(
      ContentRequestPageIds.deletePostCollection,
      'collection:${command.collectionId}:${command.expectedVersion}:delete',
    ),
  );
}
