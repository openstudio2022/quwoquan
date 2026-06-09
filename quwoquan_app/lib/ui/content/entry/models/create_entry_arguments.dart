import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';

/// 上下文化创作入口参数（经 GoRoute `extra` 传入 `/create`）。
///
/// 用于「围绕对象/圈子创作」的锚点预填：对象页传 [homepage]，圈子页传
/// [circleId]/[circleName]。锚点最终注入 `PublishSettings`，使发布 payload
/// 默认带上对象主页 / 圈子关联，降低用户绑定的心智成本。
///
/// 兼容性：`/create` 路由同时接受裸 [HomepageCanonicalReference] 作为 extra
/// （对象页历史入口），本类型用于需要携带圈子锚点的入口。
class CreateEntryArguments {
  const CreateEntryArguments({this.homepage, this.circleId, this.circleName});

  final HomepageCanonicalReference? homepage;
  final String? circleId;
  final String? circleName;
}
