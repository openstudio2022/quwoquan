import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:pretty_qr_code/pretty_qr_code.dart';
import 'package:share_plus/share_plus.dart';

import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

/// 「我的二维码」名片卡（添加我为联系人）。
///
/// 从 `edit_profile_page` 的私有 `_QrCardBody` 提升为公开复用组件，供
/// `my_qr_code_page`、`edit_profile_page` 与扫一扫页的「我的二维码」入口共用，
/// 保证名片样式单一真相源。[onScanPressed] 为空时隐藏「扫一扫」动作。
class MyQrCardView extends StatelessWidget {
  const MyQrCardView({super.key, required this.card, this.onScanPressed});

  final ProfileQrCardData card;
  final VoidCallback? onScanPressed;

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
                  label: UITextConstants.editProfileQrScanAction,
                  style: ProfileIosActionStyle.plain,
                  onPressed: onScanPressed,
                ),
              ),
            Expanded(
              child: ProfileIosActionButton(
                label: UITextConstants.editProfileQrShareAction,
                style: ProfileIosActionStyle.plain,
                onPressed: () => SharePlus.instance.share(
                  ShareParams(
                    text: card.shareText.isEmpty
                        ? card.qrPayload
                        : card.shareText,
                  ),
                ),
              ),
            ),
            Expanded(
              child: ProfileIosActionButton(
                label: UITextConstants.editProfileQrSaveAction,
                style: ProfileIosActionStyle.plain,
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: card.qrPayload));
                  if (context.mounted) {
                    AppToast.show(
                      context,
                      UITextConstants.editProfileQrSaveFallbackToast,
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
  const MyQrCardContent({super.key, required this.card});

  final ProfileQrCardData card;

  @override
  Widget build(BuildContext context) {
    return ProfileIosSectionCard(
      backgroundColor: AppColors.iosSystemBackground(context),
      padding: EdgeInsets.all(AppSpacing.containerXl),
      radius: AppSpacing.radiusTwenty,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            UITextConstants.editProfileQrCardHeading,
            style: TextStyle(
              fontSize: AppTypography.iosTitle2,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.containerXl),
          Row(
            children: <Widget>[
              _Avatar(url: card.avatarUrl, name: card.displayName),
              SizedBox(width: AppSpacing.containerMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      card.displayName,
                      style: TextStyle(
                        fontSize: AppTypography.iosTitle3,
                        fontWeight: AppTypography.semiBold,
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
          SizedBox(height: AppSpacing.containerXl),
          _QrPayloadView(data: card.qrPayload),
          SizedBox(height: AppSpacing.containerLg),
          Text(
            UITextConstants.editProfileQrCardHint,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
      ),
    );
  }
}

class _QrPayloadView extends StatelessWidget {
  const _QrPayloadView({required this.data});

  final String data;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = math.min(
          AppSpacing.threeHundredTwenty,
          constraints.maxWidth,
        );
        return Center(
          child: Container(
            width: size,
            height: size,
            color: AppColors.white,
            padding: EdgeInsets.all(AppSpacing.containerSm),
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
  const _Avatar({required this.url, required this.name});

  final String url;
  final String name;

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
                  fontSize: AppTypography.iosTitle3,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosAccent(context),
                ),
              ),
      ),
    );
    return ClipOval(
      child: SizedBox(
        width: AppSpacing.avatarUserXl,
        height: AppSpacing.avatarUserXl,
        child: url.trim().isEmpty
            ? fallback
            : AppMediaImage(
                imageSource: url,
                fit: BoxFit.cover,
                width: AppSpacing.avatarUserXl,
                height: AppSpacing.avatarUserXl,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}
