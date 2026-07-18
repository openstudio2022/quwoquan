import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// L1a 契约测试：LocationPoiDto — 覆盖 integration/location/projections/location_poi.yaml
///
/// 三维度覆盖：
///   常规契约  — 正常输入 → 正确输出（字段解析、fromMap）
///   单轨契约 — 拒旧 alias；只认 id/latitude/longitude/distanceMeters；round-trip
///   异常/边界契约 — 缺字段/null 安全、全字段缺失不崩溃
void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('LocationPoiDto — 常规契约', () {
    test('fromMap parses canonical nearby data', () {
      const raw = <String, dynamic>{
        'id': 'poi-001',
        'name': '成都·天府广场',
        'latitude': 30.6586,
        'longitude': 104.0648,
        'address': '锦江区',
        'distanceMeters': 120,
      };
      final dto = LocationPoiDto.fromMap(raw);
      expect(dto.id, equals('poi-001'));
      expect(dto.name, equals('成都·天府广场'));
      expect(dto.latitude, closeTo(30.6586, 0.0001));
      expect(dto.longitude, closeTo(104.0648, 0.0001));
      expect(dto.address, equals('锦江区'));
      expect(dto.distanceMeters, equals(120));
    });

    test('fromMap parses search result without distance', () {
      const raw = <String, dynamic>{
        'name': '成都·太古里',
        'latitude': 30.6548,
        'longitude': 104.0839,
      };
      final dto = LocationPoiDto.fromMap(raw);
      expect(dto.name, equals('成都·太古里'));
      expect(dto.latitude, closeTo(30.6548, 0.0001));
      expect(dto.longitude, closeTo(104.0839, 0.0001));
      expect(dto.distanceMeters, isNull);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 单轨契约：拒旧 alias；round-trip 只认 canonical
  // ──────────────────────────────────────────────────────────────────
  group('LocationPoiDto — 单轨契约', () {
    test('rejects _id alias when id missing', () {
      const raw = <String, dynamic>{
        '_id': 'ext-id-abc',
        'name': 'Test',
        'latitude': 1.0,
        'longitude': 2.0,
      };
      final dto = LocationPoiDto.fromMap(raw);
      expect(dto.id, equals(''));
    });

    test('rejects lat/lng alias when latitude/longitude missing', () {
      const raw = <String, dynamic>{
        'name': 'Alias POI',
        'lat': 39.9,
        'lng': 116.4,
      };
      final dto = LocationPoiDto.fromMap(raw);
      expect(dto.latitude, equals(0.0));
      expect(dto.longitude, equals(0.0));
    });

    test('rejects distance alias when distanceMeters missing', () {
      const raw = <String, dynamic>{
        'name': 'Distant POI',
        'latitude': 1.0,
        'longitude': 2.0,
        'distance': 500,
      };
      final dto = LocationPoiDto.fromMap(raw);
      expect(dto.distanceMeters, isNull);
    });

    test('toMap round-trip preserves fields', () {
      const raw = <String, dynamic>{
        'id': 'r1',
        'name': 'RoundTrip',
        'latitude': 31.2,
        'longitude': 121.5,
        'address': '浦东',
        'distanceMeters': 200,
      };
      final dto = LocationPoiDto.fromMap(raw);
      final map = dto.toMap();
      expect(map['id'], equals('r1'));
      expect(map['name'], equals('RoundTrip'));
      expect(map['latitude'], closeTo(31.2, 0.0001));
      expect(map['longitude'], closeTo(121.5, 0.0001));
      expect(map['address'], equals('浦东'));
      expect(map['distanceMeters'], equals(200));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约：缺字段/null 安全、全字段缺失不崩溃
  // ──────────────────────────────────────────────────────────────────
  group('LocationPoiDto — 异常/边界契约', () {
    test('all fields missing → fromMap returns object without crash', () {
      expect(() => LocationPoiDto.fromMap(const {}), returnsNormally);
      final dto = LocationPoiDto.fromMap(const {});
      expect(dto.id, isEmpty);
      expect(dto.name, isEmpty);
      expect(dto.latitude, equals(0.0));
      expect(dto.longitude, equals(0.0));
      expect(dto.address, equals(''));
      expect(dto.distanceMeters, isNull);
    });

    test('null values handled safely', () {
      const raw = <String, dynamic>{
        'id': null,
        'name': null,
        'latitude': null,
        'longitude': null,
        'address': null,
        'distanceMeters': null,
      };
      final dto = LocationPoiDto.fromMap(raw);
      expect(dto.id, isEmpty);
      expect(dto.name, isEmpty);
      expect(dto.latitude, equals(0.0));
      expect(dto.longitude, equals(0.0));
      expect(dto.address, equals(''));
      expect(dto.distanceMeters, isNull);
    });

    test('integer coordinates parsed to double', () {
      const raw = <String, dynamic>{
        'name': 'IntCoords',
        'latitude': 30,
        'longitude': 104,
      };
      final dto = LocationPoiDto.fromMap(raw);
      expect(dto.latitude, equals(30.0));
      expect(dto.longitude, equals(104.0));
    });
  });
}
