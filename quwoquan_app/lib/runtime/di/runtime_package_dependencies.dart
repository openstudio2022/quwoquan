import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';

enum ContentReleaseRequirement { optional, required }

/// 站外公网链接的 runtime package 边界。
///
/// 生产值只来自 [CloudRuntimeConfig]；Provider/Widget 测试可以显式交出
/// 同一业务类型，无需改写全局 runtime package。
final publicContentLinkBuilderProvider = Provider<PublicContentLinkBuilder>((
  ref,
) {
  return PublicContentLinkBuilder.fromRuntimeConfig();
});

/// Feed 空态是否必须绑定 active release 的 runtime package 边界。
final contentReleaseRequirementProvider = Provider<ContentReleaseRequirement>((
  ref,
) {
  return CloudRuntimeConfig.requiresReleaseBoundContent ||
          CloudRuntimeConfig.hasCompleteContentBinding
      ? ContentReleaseRequirement.required
      : ContentReleaseRequirement.optional;
});
