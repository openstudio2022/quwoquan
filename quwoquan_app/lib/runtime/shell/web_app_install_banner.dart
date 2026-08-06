import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/web_install_context.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

class WebAppInstallBanner extends ConsumerStatefulWidget {
  const WebAppInstallBanner({super.key});

  @override
  ConsumerState<WebAppInstallBanner> createState() =>
      _WebAppInstallBannerState();
}

class _WebAppInstallBannerState extends ConsumerState<WebAppInstallBanner> {
  var _dismissed = false;

  @override
  Widget build(BuildContext context) {
    final installContext = ref.watch(webInstallContextProvider);
    if (_dismissed ||
        installContext.dismissedForSession ||
        installContext.isStandalone) {
      return const SizedBox.shrink();
    }
    final content = _contentFor(installContext.recommendation);
    final isWide = AppSpacing.isWideLayout(context);

    return Semantics(
      container: true,
      label: '${content.title}。${content.subtitle}',
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.iosGroupedSurface(context),
          border: Border(
            bottom: BorderSide(color: AppColors.feedCardBorder(context)),
          ),
        ),
        child: SafeArea(
          bottom: false,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: AppSpacing.webInstallBannerHeight(context),
            ),
            child: Padding(
              padding: AppSpacing.webShellContentPadding(context),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: AppSpacing.webContentMaxWidth,
                  ),
                  child: Row(
                    children: [
                      Expanded(child: _InstallBannerCopy(content: content)),
                      SizedBox(width: AppSpacing.containerSm),
                      _InstallBannerActions(
                        recommendation: installContext.recommendation,
                        compact: !isWide,
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      CupertinoButton(
                        key: const ValueKey<String>('web-install-dismiss'),
                        minimumSize: const Size(
                          AppSpacing.buttonHeightSm,
                          AppSpacing.buttonHeightSm,
                        ),
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          dismissWebInstallForSession();
                          setState(() => _dismissed = true);
                        },
                        child: Icon(
                          CupertinoIcons.xmark,
                          size: AppSpacing.md,
                          color: AppColors.iosSecondaryLabel(context),
                          semanticLabel: FoundationText.close,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _InstallBannerContent {
  const _InstallBannerContent({required this.title, required this.subtitle});

  final String title;
  final String subtitle;
}

_InstallBannerContent _contentFor(WebInstallRecommendation recommendation) {
  return switch (recommendation) {
    WebInstallRecommendation.android => const _InstallBannerContent(
      title: FoundationText.webInstallBannerAndroidTitle,
      subtitle: FoundationText.webInstallBannerAndroidSubtitle,
    ),
    WebInstallRecommendation.ios => const _InstallBannerContent(
      title: FoundationText.webInstallBannerIosTitle,
      subtitle: FoundationText.webInstallBannerIosSubtitle,
    ),
    WebInstallRecommendation.desktop ||
    WebInstallRecommendation.unknown => const _InstallBannerContent(
      title: FoundationText.webInstallBannerTitle,
      subtitle: FoundationText.webInstallBannerDesktopSubtitle,
    ),
  };
}

class _InstallBannerCopy extends StatelessWidget {
  const _InstallBannerCopy({required this.content});

  final _InstallBannerContent content;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          content.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
            height: AppTypography.lineHeightTight,
          ),
        ),
        SizedBox(height: AppSpacing.two),
        Text(
          content.subtitle,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosCaption1,
            fontWeight: AppTypography.regular,
            color: AppColors.iosSecondaryLabel(context),
            height: AppTypography.lineHeightCompact,
          ),
        ),
      ],
    );
  }
}

class _InstallBannerActions extends StatelessWidget {
  const _InstallBannerActions({
    required this.recommendation,
    required this.compact,
  });

  final WebInstallRecommendation recommendation;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    switch (recommendation) {
      case WebInstallRecommendation.android:
        return _InstallActionButton(
          label: FoundationText.webInstallBannerDownload,
          onPressed: () => _open(CloudRuntimeConfig.webAppAndroidDownloadUrl),
        );
      case WebInstallRecommendation.ios:
        return _InstallActionButton(
          label: FoundationText.webInstallBannerInstall,
          onPressed: () => _open(CloudRuntimeConfig.webAppIosDownloadUrl),
        );
      case WebInstallRecommendation.desktop:
      case WebInstallRecommendation.unknown:
        if (compact) {
          return _InstallActionButton(
            label: FoundationText.webInstallBannerChoose,
            onPressed: () => _open(CloudRuntimeConfig.webAppMobileDownloadUrl),
          );
        }
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _InstallActionButton(
              label: FoundationText.webInstallBannerAndroidPackage,
              onPressed: () =>
                  _open(CloudRuntimeConfig.webAppAndroidDownloadUrl),
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            _InstallActionButton(
              label: FoundationText.webInstallBannerIosPackage,
              secondary: true,
              onPressed: () => _open(CloudRuntimeConfig.webAppIosDownloadUrl),
            ),
          ],
        );
    }
  }

  Future<void> _open(String rawUrl) async {
    final parsed = Uri.parse(rawUrl);
    final uri = parsed.hasScheme ? parsed : Uri.base.resolveUri(parsed);
    await launchUrl(uri, webOnlyWindowName: '_self');
  }
}

class _InstallActionButton extends StatelessWidget {
  const _InstallActionButton({
    required this.label,
    required this.onPressed,
    this.secondary = false,
  });

  final String label;
  final VoidCallback onPressed;
  final bool secondary;

  @override
  Widget build(BuildContext context) {
    final foreground = secondary ? AppColors.primaryColor : AppColors.white;
    final background = secondary
        ? AppColors.iosPageBackground(context)
        : AppColors.primaryColor;
    return CupertinoButton(
      minimumSize: const Size(0, AppSpacing.buttonHeightSm),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      color: background,
      borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      onPressed: onPressed,
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: foreground,
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.medium,
          height: AppTypography.lineHeightTight,
        ),
      ),
    );
  }
}
