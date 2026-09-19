// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/spec.md#sit-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/surface_layout_policy.g.dart';

void main() {
  group('SurfaceLayoutPolicy 唯一列数合同', () {
    final home = SurfaceLayoutPolicy.forSurface(ContentUiSurface.homeFeed);
    final profile = SurfaceLayoutPolicy.forSurface(
      ContentUiSurface.profileWorks,
    );

    test('首页 compact 单列，主页 compact 双列', () {
      for (final width in <double>[0, 390, 599.999]) {
        expect(home.columnsForWidth(width), 1);
        expect(profile.columnsForWidth(width), 2);
      }
    });

    test('两个 collection 面共享可用 logical pixels 与 expanded 边界', () {
      for (final entry in <double, int>{
        600: 2,
        659.999: 2,
        660: 3,
        879.999: 3,
        880: 4,
        2400: 4,
      }.entries) {
        expect(home.columnsForWidth(entry.key), entry.value);
        expect(profile.columnsForWidth(entry.key), entry.value);
      }
    });

    test('媒体与文章目的面始终为单页，不继承 collection 网格', () {
      for (final surface in <ContentUiSurface>[
        ContentUiSurface.mediaImmersive,
        ContentUiSurface.articleReader,
      ]) {
        final policy = SurfaceLayoutPolicy.forSurface(surface);
        expect(policy.layoutKind, SurfaceLayoutKind.fullBleedPager);
        for (final width in <double>[390, 600, 1440]) {
          expect(policy.columnsForWidth(width), 1);
        }
      }
    });

    test('拒绝无界或非法视口，不用默认列数掩盖调用错误', () {
      for (final width in <double>[-1, double.nan, double.infinity]) {
        expect(() => home.columnsForWidth(width), throwsArgumentError);
        expect(() => profile.columnsForWidth(width), throwsArgumentError);
      }
    });
  });
}
