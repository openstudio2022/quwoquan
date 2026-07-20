import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';

class CreateCircleService {
  const CreateCircleService();

  Future<List<CreateCircleOption>> listCircles(
    CircleRepository circleRepository,
  ) async {
    final result = await circleRepository.listCircles(limit: 20);
    final out = <CreateCircleOption>[];
    for (final dto in result) {
      if (dto.id.isEmpty || dto.name.isEmpty) continue;
      out.add(CreateCircleOption.fromCircleDto(dto));
    }
    return out;
  }
}
