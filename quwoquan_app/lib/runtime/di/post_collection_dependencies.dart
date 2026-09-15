import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/post_collection.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/application/post_collection_port.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/adapters/post_collection_remote.dart';

final postCollectionPortProvider = Provider<PostCollectionPort>(
  (ref) => RemotePostCollection(
    client: ref.watch(generatedCloudOperationClientProvider),
    queries: GeneratedPostCollectionGraphQLClient(
      ref.watch(generatedCloudOperationExecutorProvider),
    ),
    context: (pageId, key) {
      final base = contentQueryInvocationContext(
        ref,
        surface: AppUiSurfaces.postCollection,
        clientPageId: pageId,
      );
      return CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        routeId: base.routeId,
        actor: base.actor,
        idempotencyKey: key,
      );
    },
  ),
);
