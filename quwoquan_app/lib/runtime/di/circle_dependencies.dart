import 'package:quwoquan_app/circle/circle_management/circle_behavior_fact/adapters/behavior_fact_remote.dart';
import 'package:quwoquan_app/circle/circle_management/circle/adapters/circle_lifecycle_remote.dart';
import 'package:quwoquan_app/circle/circle_management/circle/adapters/circle_query_remote.dart';
import 'package:quwoquan_app/circle/circle_management/circle_file/adapters/file_remote.dart';
import 'package:quwoquan_app/circle/circle_management/circle_group/adapters/group_remote.dart';
import 'package:quwoquan_app/circle/circle_management/circle_membership/adapters/membership_remote.dart';
import 'package:quwoquan_app/circle/circle_management/circle_post_placement/adapters/post_placement_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// circle domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum CircleProductionAdapter {
  behaviorFact,
  file,
  group,
  lifecycle,
  membership,
  postPlacement,
  query,
}

/// circle domain 的唯一 production 装配入口。
final class CircleProductionComposition {
  const CircleProductionComposition._();

  static T generatedAdapter<T>(
    CircleProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      CircleProductionAdapter.behaviorFact => RemoteCircleBehaviorFactWriter(
        client: client,
        invocationContext: context,
      ),
      CircleProductionAdapter.file => RemoteCircleFileFacet(
        client: client,
        invocationContext: context,
      ),
      CircleProductionAdapter.group => RemoteCircleGroupFacet(
        client: client,
        invocationContext: context,
      ),
      CircleProductionAdapter.lifecycle => RemoteCircleLifecycleFacet(
        client: client,
        invocationContext: context,
      ),
      CircleProductionAdapter.membership => RemoteCircleMembershipFacet(
        client: client,
        invocationContext: context,
      ),
      CircleProductionAdapter.postPlacement =>
        RemoteCirclePostPlacementCommandWriter(
          client: client,
          invocationContext: context,
        ),
      CircleProductionAdapter.query => RemoteCircleQueryReader(
        client: client,
        invocationContext: context,
      ),
    };
    return result as T;
  }
}
