import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class CreateCircleService {
  const CreateCircleService();

  Future<List<CreateCircleOption>> listCircles(
    CircleQueryReader circleQuery,
  ) async {
    final result = await circleQuery.list(CircleListQuery(limit: 20));
    final out = <CreateCircleOption>[];
    for (final circle in result.items) {
      if (circle.id.isEmpty || circle.name.isEmpty) continue;
      out.add(
        CreateCircleOption(
          id: circle.id,
          name: circle.name,
          memberCount: circle.memberCount,
          postCount: circle.postCount,
          coverUrl: circle.coverUrl,
        ),
      );
    }
    return out;
  }
}
