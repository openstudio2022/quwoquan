import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_view_data.dart';

/// 上下文化创作入口参数（经 GoRoute `extra` 传入 `/create`）。
///
/// 用于「围绕对象/圈子创作」的锚点预填：对象页传 [homepage]，圈子页传
/// [circleId]/[circleName]。锚点最终注入 `PublishSettings`，使发布 payload
/// 默认带上对象主页 / 圈子关联，降低用户绑定的心智成本。
///
/// `/create` 路由只接受本类型，避免同一路由存在两种 extra 契约。
class CreateEntryArguments {
  const CreateEntryArguments({this.homepage, this.circleId, this.circleName});

  final HomepageCanonicalReference? homepage;
  final String? circleId;
  final String? circleName;
}
