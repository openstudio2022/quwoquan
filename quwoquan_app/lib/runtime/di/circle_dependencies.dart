import 'package:quwoquan_app/cloud/remote/circle/behavior_fact/behavior_fact_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/circle/circle_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/circle/circle_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/file/file_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/group/group_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/membership/membership_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/post_placement/post_placement_remote.dart';
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
