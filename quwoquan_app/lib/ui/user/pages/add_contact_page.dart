import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/ui/user/widgets/add_contact_entry_card.dart';
import 'package:quwoquan_app/ui/user/widgets/my_qr_card.dart';

/// 添加联系人主页：胶囊搜索框 + 扫一扫 / 手机联系人入口 + 我的二维码大卡。
///
/// 强入口（路由级登录门见 `requiredRouteGateForLocation`）。手机联系人入口按
/// `PlatformCapabilities.contacts` 能力位降级（Web/鸿蒙隐藏，不做平台分叉）。
class AddContactPage extends ConsumerStatefulWidget {
  const AddContactPage({super.key});

  @override
  ConsumerState<AddContactPage> createState() => _AddContactPageState();
}

class _AddContactPageState extends ConsumerState<AddContactPage> {
  late Future<ProfileQrCardData> _qrFuture;

  @override
  void initState() {
    super.initState();
    _qrFuture = ref.read(userProfileRepositoryProvider).getProfileQrCard();
  }

  void _reloadQr() {
    setState(() {
      _qrFuture = ref.read(userProfileRepositoryProvider).getProfileQrCard();
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final caps = ref.watch(platformCapabilitiesProvider);
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.home);
            }
          },
        ),
        middle: Text(
          UITextConstants.addContactSheetTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          children: <Widget>[
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => context.push(AppRoutePaths.addContactSearch()),
              child: AbsorbPointer(
                child: AppSearchField(
                  placeholder: UITextConstants.addContactSearchHubPlaceholder,
                ),
              ),
            ),
            SizedBox(height: AppSpacing.containerLg),
            _SectionCard(
              child: Column(
                children: <Widget>[
                  AddContactEntryCard(
                    icon: CupertinoIcons.qrcode_viewfinder,
                    title: UITextConstants.editProfileQrScanAction,
                    subtitle: UITextConstants.addContactScanEntrySubtitle,
                    showDivider: caps.contacts,
                    onTap: () => context.push(AppRoutePaths.addContactScan),
                  ),
                  if (caps.contacts)
                    AddContactEntryCard(
                      icon: CupertinoIcons.person_2_fill,
                      title: UITextConstants.addContactPhoneEntryTitle,
                      subtitle: UITextConstants.addContactPhoneEntrySubtitle,
                      onTap: () => context.push(AppRoutePaths.addContactPhone),
                    ),
                ],
              ),
            ),
            SizedBox(height: AppSpacing.containerLg),
            _InlineMyQrCard(future: _qrFuture, onRetry: _reloadQr),
          ],
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
      ),
      child: child,
    );
  }
}

class _InlineMyQrCard extends StatelessWidget {
  const _InlineMyQrCard({required this.future, required this.onRetry});

  final Future<ProfileQrCardData> future;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<ProfileQrCardData>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.hasData) {
          return MyQrCardContent(card: snapshot.data!, compact: true);
        }
        if (snapshot.hasError) {
          return _InlineQrStateCard(
            icon: CupertinoIcons.qrcode_viewfinder,
            title: UITextConstants.pageLoadFailedTitle,
            body: UITextConstants.pageLoadFailedMessage,
            actionLabel: UITextConstants.retry,
            onAction: onRetry,
          );
        }
        return const _InlineQrStateCard(
          icon: CupertinoIcons.qrcode,
          title: UITextConstants.editProfileQrCardTitle,
          body: UITextConstants.loading,
        );
      },
    );
  }
}

class _InlineQrStateCard extends StatelessWidget {
  const _InlineQrStateCard({
    required this.icon,
    required this.title,
    required this.body,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String title;
  final String body;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerXl),
        child: Column(
          children: <Widget>[
            Icon(
              icon,
              size: AppSpacing.iconLarge,
              color: AppColors.iosAccent(context),
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              body,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCallout,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            if (actionLabel != null && onAction != null) ...<Widget>[
              SizedBox(height: AppSpacing.containerLg),
              CupertinoButton(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerLg,
                  vertical: AppSpacing.intraGroupSm,
                ),
                borderRadius: BorderRadius.circular(
                  AppSpacing.radiusNinetyNine,
                ),
                color: AppColors.iosAccent(context),
                onPressed: onAction,
                child: Text(
                  actionLabel!,
                  style: TextStyle(
                    fontSize: AppTypography.iosCallout,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.white,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
