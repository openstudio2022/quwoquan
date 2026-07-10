import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';

Widget _buildIndicator({NetworkQuality quality = NetworkQuality.good}) {
  return ProviderScope(
    child: MaterialApp(
      home: Scaffold(
        body: Center(
          child: CallQualityIndicator(quality: quality),
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('CallQualityIndicator — 渲染契约', () {
    testWidgets('good 质量显示绿色', (tester) async {
      await tester.pumpWidget(_buildIndicator(quality: NetworkQuality.good));
      await tester.pump();

      expect(find.byType(CallQualityIndicator), findsOneWidget);

      final containers = tester.widgetList<AnimatedContainer>(
        find.byType(AnimatedContainer),
      );
      final activeContainers = containers.where((c) {
        final dec = c.decoration as BoxDecoration?;
        return dec?.color == AppColors.success;
      }).toList();
      expect(activeContainers.length, equals(4));
    });

    testWidgets('slight 质量显示警告色 3 条', (tester) async {
      await tester.pumpWidget(
        _buildIndicator(quality: NetworkQuality.slight),
      );
      await tester.pump();

      expect(find.byType(CallQualityIndicator), findsOneWidget);

      final containers = tester.widgetList<AnimatedContainer>(
        find.byType(AnimatedContainer),
      );
      final activeContainers = containers.where((c) {
        final dec = c.decoration as BoxDecoration?;
        return dec?.color == AppColors.warning;
      }).toList();
      expect(activeContainers.length, equals(3));
    });

    testWidgets('weak 质量显示橙色 2 条', (tester) async {
      await tester.pumpWidget(
        _buildIndicator(quality: NetworkQuality.weak),
      );
      await tester.pump();

      expect(find.byType(CallQualityIndicator), findsOneWidget);

      final containers = tester.widgetList<AnimatedContainer>(
        find.byType(AnimatedContainer),
      );
      final activeContainers = containers.where((c) {
        final dec = c.decoration as BoxDecoration?;
        return dec?.color == AppColors.networkCallQualityWeak;
      }).toList();
      expect(activeContainers.length, equals(2));
    });

    testWidgets('poor 质量显示红色 1 条', (tester) async {
      await tester.pumpWidget(
        _buildIndicator(quality: NetworkQuality.poor),
      );
      await tester.pump();

      expect(find.byType(CallQualityIndicator), findsOneWidget);

      final containers = tester.widgetList<AnimatedContainer>(
        find.byType(AnimatedContainer),
      );
      final activeContainers = containers.where((c) {
        final dec = c.decoration as BoxDecoration?;
        return dec?.color == AppColors.error;
      }).toList();
      expect(activeContainers.length, equals(1));
    });

    testWidgets('始终渲染 4 个 AnimatedContainer 信号柱', (tester) async {
      for (final quality in NetworkQuality.values) {
        await tester.pumpWidget(_buildIndicator(quality: quality));
        await tester.pump();

        expect(
          find.byType(AnimatedContainer),
          findsNWidgets(4),
          reason: 'should have 4 bars for ${quality.name}',
        );
      }
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('CallQualityIndicator — 交互契约', () {
    testWidgets('质量切换有动画过渡', (tester) async {
      await tester.pumpWidget(_buildIndicator(quality: NetworkQuality.good));
      await tester.pump();

      await tester.pumpWidget(_buildIndicator(quality: NetworkQuality.poor));
      await tester.pump(const Duration(milliseconds: 150));

      expect(find.byType(CallQualityIndicator), findsOneWidget);
      expect(find.byType(AnimatedContainer), findsNWidgets(4));
    });

    testWidgets('barCount 属性与 NetworkQuality 一致', (tester) async {
      expect(NetworkQuality.good.barCount, 4);
      expect(NetworkQuality.slight.barCount, 3);
      expect(NetworkQuality.weak.barCount, 2);
      expect(NetworkQuality.poor.barCount, 1);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('CallQualityIndicator — 错误态渲染', () {
    testWidgets('默认 good 质量不崩溃', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: const Center(child: CallQualityIndicator()),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(CallQualityIndicator), findsOneWidget);
    });

    testWidgets('每种质量级别颜色正确', (tester) async {
      expect(NetworkQuality.good.color, equals(AppColors.success));
      expect(NetworkQuality.slight.color, equals(AppColors.warning));
      expect(NetworkQuality.weak.color, equals(const Color(0xFFFF6B35)));
      expect(NetworkQuality.poor.color, equals(AppColors.error));
    });
  });
}
