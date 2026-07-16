import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';

class CreateCircleService {
  const CreateCircleService();

  Future<List<CreateCircleOption>> listCircles(
    CircleRepository circleRepository,
  ) async {
    try {
      final result = await circleRepository.listCircles(limit: 20);
      if (result.isNotEmpty) {
        final out = <CreateCircleOption>[];
        for (final dto in result) {
          if (dto.id.isEmpty || dto.name.isEmpty) continue;
          out.add(CreateCircleOption.fromCircleDto(dto));
        }
        if (out.isNotEmpty) return out;
      }
    } catch (_) {
      return const <CreateCircleOption>[];
    }
    return const <CreateCircleOption>[];
  }
}

List<CreateCircleOption> publishFlowRecommendedCircleOptions(
  CircleRepository circles,
) {
  final dtos = circles.publishFlowRecommendedCircles();
  if (dtos.isEmpty) return const <CreateCircleOption>[];
  const reasons = <String, String>{'rec-city': '与你兴趣相似', 'rec-run': '同城热门'};
  return dtos
      .map(
        (dto) => CreateCircleOption.fromCircleDto(
          dto,
          isJoined: false,
          recommendationReason: reasons[dto.id],
        ),
      )
      .toList(growable: false);
}
