import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

void main() {
  testWidgets('导航尺寸、安全区与 Web 横幅保持四档响应式契约', (tester) async {
    Future<(double, double, double, double)> resolveAt(double width) async {
      late double iconSize;
      late double bannerHeight;
      late double topSafeInset;
      late double bottomSideInset;
      await tester.pumpWidget(
        MediaQuery(
          data: MediaQueryData(size: Size(width, 800)),
          child: Builder(
            builder: (context) {
              iconSize = AppSpacing.bottomNavBarItemIconSize(context);
              bannerHeight = AppSpacing.webInstallBannerHeight(context);
              topSafeInset = AppSpacing.primaryTopBarSafeTopInset(44, context);
              bottomSideInset = AppSpacing.bottomNavContentSideInset(
                context,
                24,
              );
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      return (iconSize, bannerHeight, topSafeInset, bottomSideInset);
    }

    expect(await resolveAt(320), (
      AppSpacing.iconMedium,
      AppSpacing.webInstallBannerCompactHeight,
      33.0,
      16.0,
    ));
    expect(await resolveAt(390), (
      AppSpacing.twentyEight,
      AppSpacing.webInstallBannerCompactHeight,
      33.0,
      12.0,
    ));
    expect(await resolveAt(820), (
      AppSpacing.iconLarge,
      AppSpacing.webInstallBannerCompactHeight,
      31.0,
      16.0,
    ));
    expect(await resolveAt(1200), (
      AppSpacing.forty,
      AppSpacing.webInstallBannerWideHeight,
      31.0,
      16.0,
    ));
  });
}
