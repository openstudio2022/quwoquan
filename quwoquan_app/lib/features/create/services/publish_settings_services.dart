import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/features/create/models/publish_settings_models.dart';

enum MapProviderType { baidu, amap }

class CreateLocationService {
  const CreateLocationService();

  MapProviderType get currentProvider {
    final raw = CloudRuntimeConfig.mapProvider.toLowerCase().trim();
    if (raw == 'amap' || raw == 'ali' || raw == 'alimap') {
      return MapProviderType.amap;
    }
    return MapProviderType.baidu;
  }

  Future<List<CreateLocationOption>> nearby() async {
    final base = currentProvider == MapProviderType.amap
        ? _amapNearby
        : _baiduNearby;
    return base;
  }

  Future<List<CreateLocationOption>> search(String keyword) async {
    final q = keyword.trim().toLowerCase();
    if (q.isEmpty) return nearby();
    final base = currentProvider == MapProviderType.amap
        ? _amapNearby
        : _baiduNearby;
    return base.where((item) => item.name.toLowerCase().contains(q)).toList();
  }
}

class CreateCircleService {
  const CreateCircleService();

  Future<List<CreateCircleOption>> listCircles(DataService dataService) async {
    try {
      final result = await dataService.getDataList(
        endpoint: '/circles',
        limit: 20,
      );
      if (result.isNotEmpty) {
        return result
            .map(
              (item) => CreateCircleOption(
                id: (item['id'] ?? '').toString(),
                name: (item['name'] ?? item['title'] ?? '').toString(),
              ),
            )
            .where((item) => item.id.isNotEmpty && item.name.isNotEmpty)
            .toList();
      }
    } catch (_) {
      // ignore and fallback
    }
    return _mockCircles;
  }
}

const List<CreateLocationOption> _baiduNearby = <CreateLocationOption>[
  CreateLocationOption(name: '成都·天府广场', latitude: 30.6586, longitude: 104.0648),
  CreateLocationOption(name: '成都·春熙路', latitude: 30.6570, longitude: 104.0822),
  CreateLocationOption(name: '成都·太古里', latitude: 30.6548, longitude: 104.0839),
  CreateLocationOption(name: '成都·望平街', latitude: 30.6662, longitude: 104.0956),
];

const List<CreateLocationOption> _amapNearby = <CreateLocationOption>[
  CreateLocationOption(
    name: '成都·IFS国金中心',
    latitude: 30.6591,
    longitude: 104.0837,
  ),
  CreateLocationOption(name: '成都·宽窄巷子', latitude: 30.6673, longitude: 104.0547),
  CreateLocationOption(name: '成都·东郊记忆', latitude: 30.6647, longitude: 104.1278),
  CreateLocationOption(name: '成都·九眼桥', latitude: 30.6479, longitude: 104.0915),
];

const List<CreateCircleOption> _mockCircles = <CreateCircleOption>[
  CreateCircleOption(id: 'circle-photo', name: '摄影圈'),
  CreateCircleOption(id: 'circle-travel', name: '旅行圈'),
  CreateCircleOption(id: 'circle-food', name: '美食圈'),
  CreateCircleOption(id: 'circle-citywalk', name: 'CityWalk圈'),
  CreateCircleOption(id: 'circle-video', name: '短视频创作圈'),
  CreateCircleOption(id: 'circle-article', name: '图文写作圈'),
];
