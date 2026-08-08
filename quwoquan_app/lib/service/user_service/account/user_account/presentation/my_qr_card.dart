import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:pretty_qr_code/pretty_qr_code.dart';

import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';

typedef ProfileQrSharePresenter =
    Future<void> Function(BuildContext context, ProfileQrShareRequest request);
typedef ProfileQrCardValidator = void Function(ProfileQrCardData card);

final class ProfileQrShareRequest {
  const ProfileQrShareRequest({
    required this.card,
    required this.title,
    required this.shareMessage,
    required this.previewBuilder,
  });

  final ProfileQrCardData card;
  final String title;
  final String shareMessage;
  final WidgetBuilder previewBuilder;
}

/// 「我的二维码」名片卡（添加我为联系人）。
///
/// 从 `edit_profile_page` 的私有 `_QrCardBody` 提升为公开复用组件，供
/// `my_qr_code_page`、`edit_profile_page` 与扫一扫页的「我的二维码」入口共用，
/// 保证名片样式单一真相源。[onScanPressed] 为空时隐藏「扫一扫」动作。
class MyQrCardView extends StatelessWidget {
  const MyQrCardView({
    super.key,
    required this.card,
    required this.sharePresenter,
    this.onScanPressed,
    this.validateCard,
    this.onValidationRetry,
  });

  final ProfileQrCardData card;
  final ProfileQrSharePresenter sharePresenter;
  final VoidCallback? onScanPressed;
  final ProfileQrCardValidator? validateCard;
  final VoidCallback? onValidationRetry;

  Future<bool> _validateForAction(BuildContext context) async {
    try {
      validateCard?.call(card);
      return true;
    } catch (error) {
      if (!context.mounted) {
        return false;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: ensureRetryUiErrorSemantic(
          runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.submit,
            scope: UiErrorScope.dialog,
          ),
        ),
        onAction: onValidationRetry == null
            ? null
            : (action) async {
                if (action.type == UiErrorActionType.retry ||
                    action.type == UiErrorActionType.resubmit) {
                  onValidationRetry!();
                }
              },
      );
      return false;
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      children: <Widget>[
        MyQrCardContent(card: card),
        SizedBox(height: AppSpacing.containerXl),
        Row(
          children: <Widget>[
            if (onScanPressed != null)
              Expanded(
                child: ProfileIosActionButton(
                  label: ProfileText.editProfileQrScanAction,
                  style: ProfileIosActionStyle.plain,
                  onPressed: onScanPressed,
                ),
              ),
            Expanded(
              child: ProfileIosActionButton(
                label: ProfileText.editProfileQrShareAction,
                style: ProfileIosActionStyle.plain,
                onPressed: () async {
                  if (!await _validateForAction(context) || !context.mounted) {
                    return;
                  }
                  await sharePresenter(
                    context,
                    ProfileQrShareRequest(
                      card: card,
                      title: UITextConstants.profileQrForwardTitle(
                        card.displayName,
                      ),
                      shareMessage: card.shareText.trim().isNotEmpty
                          ? card.shareText.trim()
                          : card.qrPayload.trim(),
                      previewBuilder: (_) =>
                          ProfileQrForwardPreview(card: card),
                    ),
                  );
                },
              ),
            ),
            Expanded(
              child: ProfileIosActionButton(
                label: ProfileText.editProfileQrSaveAction,
                style: ProfileIosActionStyle.plain,
                onPressed: () async {
                  if (!await _validateForAction(context)) {
                    return;
                  }
                  await Clipboard.setData(ClipboardData(text: card.qrPayload));
                  if (context.mounted) {
                    AppToast.show(
                      context,
                      ProfileText.editProfileQrSaveFallbackToast,
                    );
                  }
                },
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// 我的二维码卡片主体。独立页与添加联系人主页共用，避免二维码样式形成第二套实现。
class MyQrCardContent extends StatelessWidget {
  const MyQrCardContent({super.key, required this.card, this.compact = false});

  final ProfileQrCardData card;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final cardPadding = EdgeInsets.all(
      compact ? AppSpacing.containerLg : AppSpacing.containerXl,
    );
    final headingFontSize = compact
        ? AppTypography.iosBody
        : AppTypography.iosNavTitle;
    final headingWeight = compact
        ? AppTypography.regular
        : AppTypography.semiBold;
    final avatarSize = compact
        ? AppSpacing.avatarUserLg
        : AppSpacing.avatarUserLg;
    final nameFontSize = compact
        ? AppTypography.iosBody
        : AppTypography.iosBody;
    final nameWeight = compact ? AppTypography.regular : AppTypography.semiBold;
    final qrMaxSize = compact
        ? AppSpacing.twoHundredTwenty
        : AppSpacing.threeHundredTwenty;
    final qrPadding = compact ? AppSpacing.containerXs : AppSpacing.containerSm;
    return ProfileIosSectionCard(
      backgroundColor: AppColors.iosSystemBackground(context),
      padding: cardPadding,
      radius: AppSpacing.radiusTwenty,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            ProfileText.editProfileQrCardHeading,
            style: TextStyle(
              fontSize: headingFontSize,
              fontWeight: headingWeight,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(
            height: compact ? AppSpacing.containerLg : AppSpacing.containerXl,
          ),
          Row(
            children: <Widget>[
              _Avatar(
                url: card.avatarUrl,
                name: card.displayName,
                size: avatarSize,
                initialFontSize: nameFontSize,
              ),
              SizedBox(width: AppSpacing.containerMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      card.displayName,
                      style: TextStyle(
                        fontSize: nameFontSize,
                        fontWeight: nameWeight,
                        color: AppColors.iosLabel(context),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (card.region.isNotEmpty) ...<Widget>[
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        card.region,
                        style: TextStyle(
                          fontSize: AppTypography.iosSubheadline,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          SizedBox(
            height: compact ? AppSpacing.containerLg : AppSpacing.containerXl,
          ),
          _QrPayloadView(
            data: card.qrPayload,
            maxSize: qrMaxSize,
            padding: qrPadding,
          ),
          if (!compact) ...<Widget>[
            SizedBox(height: AppSpacing.containerMd),
            Text(
              ProfileText.editProfileQrCardHint,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class ProfileQrForwardPreview extends StatelessWidget {
  const ProfileQrForwardPreview({super.key, required this.card});

  final ProfileQrCardData card;

  @override
  Widget build(BuildContext context) {
    final qrPreviewSize =
        AppSpacing.twoHundredTwenty - AppSpacing.largeButtonSize;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        border: Border.all(
          color: AppColors.iosSeparator(context),
          width: AppSpacing.hairline,
        ),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                _Avatar(
                  url: card.avatarUrl,
                  name: card.displayName,
                  size: AppSpacing.avatarUserMd,
                  initialFontSize: AppTypography.iosFootnote,
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Expanded(
                  child: Text(
                    card.displayName,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.containerSm),
            _QrPayloadView(
              data: card.qrPayload,
              maxSize: qrPreviewSize,
              padding: AppSpacing.intraGroupXs,
            ),
          ],
        ),
      ),
    );
  }
}

class _QrPayloadView extends StatelessWidget {
  const _QrPayloadView({
    required this.data,
    required this.maxSize,
    required this.padding,
  });

  final String data;
  final double maxSize;
  final double padding;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = math.min(maxSize, constraints.maxWidth);
        return Center(
          child: Container(
            width: size,
            height: size,
            color: AppColors.white,
            padding: EdgeInsets.all(padding),
            child: PrettyQrView.data(
              data: data,
              errorCorrectLevel: QrErrorCorrectLevel.M,
              decoration: PrettyQrDecoration(
                shape: PrettyQrSmoothSymbol(
                  color: AppColors.iosAccent(context),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({
    required this.url,
    required this.name,
    required this.size,
    required this.initialFontSize,
  });

  final String url;
  final String name;
  final double size;
  final double initialFontSize;

  @override
  Widget build(BuildContext context) {
    final initial = name.trim().isNotEmpty
        ? name.trim().characters.first.toUpperCase()
        : '';
    final fallback = ColoredBox(
      color: AppColors.iosAccent(context).withValues(alpha: 0.12),
      child: Center(
        child: initial.isEmpty
            ? Icon(
                CupertinoIcons.person_fill,
                size: AppSpacing.iconMedium,
                color: AppColors.iosAccent(context),
              )
            : Text(
                initial,
                style: TextStyle(
                  fontSize: initialFontSize,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosAccent(context),
                ),
              ),
      ),
    );
    return ClipOval(
      child: SizedBox(
        width: size,
        height: size,
        child: url.trim().isEmpty
            ? fallback
            : AppMediaImage(
                imageSource: url,
                fit: BoxFit.cover,
                width: size,
                height: size,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}
