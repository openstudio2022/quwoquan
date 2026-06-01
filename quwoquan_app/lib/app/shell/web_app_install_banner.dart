import 'package:flutter/cupertino.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class WebAppInstallBanner extends StatelessWidget {
  const WebAppInstallBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final isWide = AppSpacing.isWideLayout(context);
    final height = AppSpacing.webInstallBannerHeight(context);
    final horizontalPadding = AppSpacing.webShellContentPadding(context);
    final subtitle = isWide
        ? UITextConstants.webInstallBannerDesktopSubtitle
        : UITextConstants.webInstallBannerMobileSubtitle;

    return Semantics(
      container: true,
      label: UITextConstants.webInstallBannerTitle,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.iosGroupedSurface(context),
          border: Border(
            bottom: BorderSide(color: AppColors.feedCardBorder(context)),
          ),
        ),
        child: SafeArea(
          bottom: false,
          child: SizedBox(
            height: height,
            child: Padding(
              padding: horizontalPadding,
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: AppSpacing.webContentMaxWidth,
                  ),
                  child: Row(
                    children: [
                      const _InstallBrandMark(),
                      SizedBox(width: AppSpacing.containerSm),
                      Expanded(
                        child: _InstallBannerCopy(
                          subtitle: subtitle,
                          compact: !isWide,
                        ),
                      ),
                      SizedBox(width: AppSpacing.containerSm),
                      _InstallBannerActions(isWide: isWide),
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

class _InstallBrandMark extends StatelessWidget {
  const _InstallBrandMark();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: const SizedBox(
        width: AppSpacing.forty,
        height: AppSpacing.forty,
        child: Icon(
          CupertinoIcons.sparkles,
          color: AppColors.assistantMarkColor,
          size: AppSpacing.twenty,
        ),
      ),
    );
  }
}

class _InstallBannerCopy extends StatelessWidget {
  const _InstallBannerCopy({required this.subtitle, required this.compact});

  final String subtitle;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final titleStyle = TextStyle(
      fontSize: AppTypography.iosSubheadline,
      fontWeight: AppTypography.semiBold,
      color: AppColors.iosLabel(context),
      height: AppTypography.lineHeightTight,
    );
    final subtitleStyle = TextStyle(
      fontSize: AppTypography.iosCaption1,
      fontWeight: AppTypography.regular,
      color: AppColors.iosSecondaryLabel(context),
      height: AppTypography.lineHeightCompact,
    );

    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          UITextConstants.webInstallBannerTitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: titleStyle,
        ),
        if (!compact) ...[
          SizedBox(height: AppSpacing.two),
          Text(
            subtitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: subtitleStyle,
          ),
        ],
      ],
    );
  }
}

class _InstallBannerActions extends StatelessWidget {
  const _InstallBannerActions({required this.isWide});

  final bool isWide;

  @override
  Widget build(BuildContext context) {
    if (isWide) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _InstallActionButton(
            label: UITextConstants.webInstallBannerIosPackage,
            onPressed: () => _open(CloudRuntimeConfig.webAppIosDownloadUrl),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          _InstallActionButton(
            label: UITextConstants.webInstallBannerAndroidPackage,
            onPressed: () =>
                _open(CloudRuntimeConfig.webAppAndroidDownloadUrl),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          _InstallActionButton(
            label: UITextConstants.webInstallBannerShareInstall,
            secondary: true,
            onPressed: _shareInstallPage,
          ),
        ],
      );
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _InstallActionButton(
          label: UITextConstants.webInstallBannerDownloadApp,
          onPressed: () => _open(CloudRuntimeConfig.webAppMobileDownloadUrl),
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        _InstallActionButton(
          label: UITextConstants.share,
          secondary: true,
          onPressed: _shareInstallPage,
        ),
      ],
    );
  }

  Future<void> _open(String rawUrl) async {
    final parsed = Uri.parse(rawUrl);
    final uri = parsed.hasScheme ? parsed : Uri.base.resolveUri(parsed);
    await launchUrl(uri, webOnlyWindowName: '_self');
  }

  Future<void> _shareInstallPage() async {
    await SharePlus.instance.share(
      ShareParams(
        text:
            '${UITextConstants.webInstallBannerTitle}：'
            '${CloudRuntimeConfig.webAppShareInstallUrl}',
      ),
    );
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
    final color = secondary ? AppColors.iosLabel(context) : AppColors.white;
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
          color: color,
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.medium,
          height: AppTypography.lineHeightTight,
        ),
      ),
    );
  }
}
