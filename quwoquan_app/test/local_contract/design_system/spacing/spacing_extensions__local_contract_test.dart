import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/spacing_extensions.dart';

void main() {
  /// 三个扩展方法都只依赖 SpacingSize 语义档位，不读 MediaQuery；
  /// 这里只需要一个真实 BuildContext 就能逐档取值。
  Future<Map<SpacingSize, (double, double, double)>> resolveAllSizes(
    WidgetTester tester,
  ) async {
    final resolved = <SpacingSize, (double, double, double)>{};
    await tester.pumpWidget(
      Builder(
        builder: (context) {
          for (final size in SpacingSize.values) {
            resolved[size] = (
              context.safeGetIntraGroupSpacing(size),
              context.safeGetInterGroupSpacing(size),
              context.safeGetContainerSpacing(size),
            );
          }
          return const SizedBox.shrink();
        },
      ),
    );
    return resolved;
  }

  testWidgets('SpacingExtension 逐档给出组内/组间/容器三套间距', (tester) async {
    final resolved = await resolveAllSizes(tester);

    // 组内间距直接落到基础档位值。
    expect(resolved[SpacingSize.xs]!.$1, AppSpacing.xs);
    expect(resolved[SpacingSize.sm]!.$1, AppSpacing.sm);
    expect(resolved[SpacingSize.md]!.$1, AppSpacing.md);
    expect(resolved[SpacingSize.lg]!.$1, AppSpacing.lg);
    expect(resolved[SpacingSize.xl]!.$1, AppSpacing.xl);

    // 组间间距是同档组内间距的两倍。
    for (final size in SpacingSize.values) {
      expect(resolved[size]!.$2, resolved[size]!.$1 * 2);
    }

    // 容器间距只在 xs/sm 加倍，md 及以上与基础档位一致。
    expect(resolved[SpacingSize.xs]!.$3, AppSpacing.xs * 2);
    expect(resolved[SpacingSize.sm]!.$3, AppSpacing.sm * 2);
    expect(resolved[SpacingSize.md]!.$3, AppSpacing.md);
    expect(resolved[SpacingSize.lg]!.$3, AppSpacing.lg);
    expect(resolved[SpacingSize.xl]!.$3, AppSpacing.xl);
  });

  testWidgets('三套间距在档位间严格单调递增', (tester) async {
    final resolved = await resolveAllSizes(tester);
    final ordered = SpacingSize.values;

    for (var i = 1; i < ordered.length; i++) {
      expect(
        resolved[ordered[i]]!.$1,
        greaterThan(resolved[ordered[i - 1]]!.$1),
        reason: '组内间距应随档位递增：${ordered[i]}',
      );
      expect(
        resolved[ordered[i]]!.$2,
        greaterThan(resolved[ordered[i - 1]]!.$2),
        reason: '组间间距应随档位递增：${ordered[i]}',
      );
    }
  });
}
