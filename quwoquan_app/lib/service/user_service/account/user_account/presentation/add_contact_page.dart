import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/add_contact_entry_card.dart';
import 'package:quwoquan_app/runtime/di/presentation/my_qr_card.dart';

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
  late Future<ContactDiscoveryResultView?> _latestDiscoveryFuture;

  @override
  void initState() {
    super.initState();
    _qrFuture = ref
        .read(profileEditQueryProvider(AppUiSurfaces.addContact))
        .getProfileQrCard();
    _latestDiscoveryFuture = ref
        .read(contactDiscoveryRepositoryProvider)
        .getLatest();
  }

  void _reloadLatestDiscovery() {
    setState(() {
      _latestDiscoveryFuture = ref
          .read(contactDiscoveryRepositoryProvider)
          .getLatest();
    });
  }

  Future<void> _dismissLatest(ContactDiscoveryResultView result) async {
    try {
      await ref.read(contactDiscoveryRepositoryProvider).dismiss(result.id);
      if (!mounted) {
        return;
      }
      setState(() {
        _latestDiscoveryFuture = Future<ContactDiscoveryResultView?>.value(
          null,
        );
      });
      AppToast.show(context, ContentText.addContactRecentDiscoveryDismissed);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'contact_discovery',
              action: 'dismiss_latest',
              pageName: 'AddContactPage',
              targetType: 'contact_discovery',
              targetKey: result.id,
            ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _dismissLatest(result);
          }
        },
      );
    }
  }

  void _openEntry(String action, String location) {
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'contact_discovery',
            action: action,
            pageName: 'AddContactPage',
          ),
    );
    context.push(location);
  }

  void _openSearch() {
    _openEntry('open_contact_search', AppRoutePaths.addContactSearch());
  }

  void _reloadQr() {
    setState(() {
      _qrFuture = ref
          .read(profileEditQueryProvider(AppUiSurfaces.addContact))
          .getProfileQrCard();
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
          ContactText.addContactSheetTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          children: <Widget>[
            Semantics(
              key: const ValueKey<String>('add-contact-search-entry'),
              button: true,
              label: ContactText.addContactSearchHubPlaceholder,
              onTap: _openSearch,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: _openSearch,
                child: AbsorbPointer(
                  child: AppSearchField(
                    placeholder: ContactText.addContactSearchHubPlaceholder,
                  ),
                ),
              ),
            ),
            SizedBox(height: AppSpacing.containerLg),
            _SectionCard(
              child: Column(
                children: <Widget>[
                  AddContactEntryCard(
                    icon: CupertinoIcons.qrcode_viewfinder,
                    title: ProfileText.editProfileQrScanAction,
                    subtitle: ContactText.addContactScanEntrySubtitle,
                    showDivider: caps.contacts,
                    onTap: () => _openEntry(
                      'open_contact_scan',
                      AppRoutePaths.addContactScan,
                    ),
                  ),
                  if (caps.contacts)
                    AddContactEntryCard(
                      icon: CupertinoIcons.person_2_fill,
                      title: ContactText.addContactPhoneEntryTitle,
                      subtitle: ContactText.addContactPhoneEntrySubtitle,
                      onTap: () => _openEntry(
                        'open_phone_contacts',
                        AppRoutePaths.addContactPhone,
                      ),
                    ),
                ],
              ),
            ),
            SizedBox(height: AppSpacing.containerLg),
            _LatestContactDiscoveryCard(
              future: _latestDiscoveryFuture,
              onDismiss: (result) => unawaited(_dismissLatest(result)),
              onRetry: _reloadLatestDiscovery,
            ),
            SizedBox(height: AppSpacing.containerLg),
            _InlineMyQrCard(future: _qrFuture, onRetry: _reloadQr),
          ],
        ),
      ),
    );
  }
}

class _LatestContactDiscoveryCard extends StatelessWidget {
  const _LatestContactDiscoveryCard({
    required this.future,
    required this.onDismiss,
    required this.onRetry,
  });

  final Future<ContactDiscoveryResultView?> future;
  final ValueChanged<ContactDiscoveryResultView> onDismiss;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<ContactDiscoveryResultView?>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return AppSectionErrorCard(
            semantic: runtimeErrorSemantic(
              context,
              error: snapshot.error!,
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
              presentation: UiErrorPresentation.sectionSoftCard,
            ),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                onRetry();
              }
            },
          );
        }
        if (snapshot.connectionState != ConnectionState.done) {
          return const _InlineQrStateCard(
            icon: CupertinoIcons.person_2,
            title: ContentText.addContactRecentDiscoveryTitle,
            body: FoundationText.loading,
          );
        }
        final result = snapshot.data;
        if (result == null ||
            result.id.isEmpty ||
            result.status == 'dismissed' ||
            result.status == 'expired') {
          return const SizedBox.shrink();
        }
        return DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.iosSystemBackground(context),
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          ),
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.containerMd),
            child: Row(
              children: <Widget>[
                Icon(
                  CupertinoIcons.person_2_fill,
                  color: AppColors.iosAccent(context),
                  size: AppSpacing.iconMedium,
                ),
                SizedBox(width: AppSpacing.interGroupSm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        ContentText.addContactRecentDiscoveryTitle,
                        style: TextStyle(
                          color: AppColors.iosLabel(context),
                          fontSize: AppTypography.iosBody,
                          fontWeight: AppTypography.semiBold,
                        ),
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        UITextConstants.phoneContactsMatchedCount(
                          result.matchCount,
                        ),
                        style: TextStyle(
                          color: AppColors.iosSecondaryLabel(context),
                          fontSize: AppTypography.iosFootnote,
                        ),
                      ),
                    ],
                  ),
                ),
                CupertinoButton(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                  ),
                  onPressed: () => onDismiss(result),
                  child: const Text(
                    ContentText.addContactRecentDiscoveryDismiss,
                  ),
                ),
              ],
            ),
          ),
        );
      },
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
          return AppSectionErrorCard(
            semantic: runtimeErrorSemantic(
              context,
              error: snapshot.error!,
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
              presentation: UiErrorPresentation.sectionSoftCard,
            ),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                onRetry();
              }
            },
          );
        }
        return const _InlineQrStateCard(
          icon: CupertinoIcons.qrcode,
          title: ProfileText.editProfileQrCardTitle,
          body: FoundationText.loading,
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
  });

  final IconData icon;
  final String title;
  final String body;

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
          ],
        ),
      ),
    );
  }
}
