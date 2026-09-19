import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 合集应用只消费 canonical generated 请求与结果，不复制 wire 模型。
abstract interface class PostCollectionPort {
  Future<PostCollectionPage> get(GetPostCollectionQuery query);
  Future<PostCollectionManagementView> management(
    GetPostCollectionManagementQuery query,
  );
  Future<AuthorPostPageSlice> authorPosts(ContentAuthorPostsQuery query);
  Future<PostCollectionCommandResult> save(SavePostCollectionCommand command);
  Future<PostCollectionCommandResult> delete(
    DeletePostCollectionCommand command,
  );
}
