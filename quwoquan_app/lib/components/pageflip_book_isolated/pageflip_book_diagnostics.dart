import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/widgets/pageflip_book_widget.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

class PageflipBookIsolatedDiagnosticsApp extends StatelessWidget {
  const PageflipBookIsolatedDiagnosticsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: PageflipBookIsolatedDiagnosticsPage(),
    );
  }
}

class PageflipBookIsolatedDiagnosticsPage extends StatelessWidget {
  const PageflipBookIsolatedDiagnosticsPage({super.key});

  static const _demoPages = <_DiagnosticsPageData>[
    _DiagnosticsPageData(
      title: '前言',
      accent: AppColors.imageEditorHslOrange,
      body: '这是隔离 pageflip 组件的隐藏验收入口。当前版本只验证手机单页 mesh-only，左半区回翻，右半区前翻。',
    ),
    _DiagnosticsPageData(
      title: '第一章',
      accent: AppColors.imageEditorHslBlue,
      body: 'Backward 的目标不是扫描切页，而是以前翻同一引擎的逆向过程完成遮挡、卷起、背页展开。',
    ),
    _DiagnosticsPageData(
      title: '第二章',
      accent: AppColors.imageEditorHslRed,
      body:
          '本页用于观察 quarter、half、three-quarter 三个阶段是否持续命中 mesh renderer，而不是回落到平面分片。',
    ),
    _DiagnosticsPageData(
      title: '尾声',
      accent: AppColors.imageEditorHslGreen,
      body: '该入口不会替换正式阅读器，只用于对照、手动验收和集成测试。',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      backgroundColor: AppColors.welcomeBackgroundDark,
      child: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.twenty,
                AppSpacing.md,
                AppSpacing.twenty,
                AppSpacing.ten + AppSpacing.two,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Pageflip Isolated Diagnostics',
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.iosTitle3,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    '左半区点击或右滑观察 backward，右半区点击或左滑观察 forward。正式阅读器入口保持不变。',
                    style: TextStyle(
                      color: AppColors.worksBodyText,
                      fontSize: AppTypography.smPlus,
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.md,
                  AppSpacing.zero,
                  AppSpacing.md,
                  AppSpacing.md,
                ),
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.worksDrawerBg,
                    borderRadius: BorderRadius.circular(AppSpacing.containerXl),
                  ),
                  child: PageflipBookIsolated(
                    pageCount: _demoPages.length,
                    initialPage: 1,
                    pageAspectRatio: 0.72,
                    pageBuilder: (context, pageIndex, pageSize) {
                      final data = _demoPages[pageIndex];
                      return _DiagnosticsPageCard(
                        data: data,
                        pageIndex: pageIndex,
                      );
                    },
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DiagnosticsPageCard extends StatelessWidget {
  const _DiagnosticsPageCard({required this.data, required this.pageIndex});

  final _DiagnosticsPageData data;
  final int pageIndex;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurfaceLight,
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
        border: Border.all(color: AppColors.iosPopupHairlineSeparatorLight),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.15),
            blurRadius: AppSpacing.eighteen,
            offset: const Offset(0, AppSpacing.sm),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg,
          AppSpacing.twentyEight,
          AppSpacing.lg,
          AppSpacing.lg,
        ),
        child: DefaultTextStyle(
          style: TextStyle(
            color: AppColors.iosPopupPrimaryLabelOnLight,
            height: AppSpacing.textLineHeightArticleBody,
            fontSize: AppTypography.lg,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                width: AppSpacing.largeButtonSize,
                height: AppSpacing.six,
                decoration: BoxDecoration(
                  color: data.accent,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
                ),
              ),
              const SizedBox(height: AppSpacing.twenty),
              Text(
                data.title,
                style: TextStyle(
                  fontSize: AppTypography.iosProfileTitle,
                  fontWeight: FontWeight.w700,
                  color: AppColors.createMediaFallbackGradientBottom,
                ),
              ),
              const SizedBox(height: AppSpacing.sm + AppSpacing.two),
              Text(
                '第 ${pageIndex + 1} 页',
                style: TextStyle(
                  color: data.accent.withValues(alpha: 0.9),
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: AppSpacing.twenty),
              Text(data.body),
              const Spacer(),
              Divider(
                color: AppColors.iosPopupHairlineSeparatorLight,
                height: AppSpacing.one,
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      'Mesh-only / Single Page / Hidden Entry',
                      style: TextStyle(
                        color: data.accent.withValues(alpha: 0.95),
                        fontSize: AppTypography.sm,
                        fontWeight: FontWeight.w700,
                        letterSpacing: AppSpacing.three / AppTypography.sm,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DiagnosticsPageData {
  const _DiagnosticsPageData({
    required this.title,
    required this.accent,
    required this.body,
  });

  final String title;
  final Color accent;
  final String body;
}
