import 'dart:async';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/my_qr_card.dart';

/// 我的二维码独立页：复用 [MyQrCardView]，扫一扫按钮跳转扫码页。
class MyQrCodePage extends ConsumerStatefulWidget {
  const MyQrCodePage({super.key, required this.sharePresenter, this.clock});

  final ProfileQrSharePresenter sharePresenter;
  final DateTime Function()? clock;

  @override
  ConsumerState<MyQrCodePage> createState() => _MyQrCodePageState();
}

class _MyQrCodePageState extends ConsumerState<MyQrCodePage> {
  late Future<ProfileQrCardData> _future;

  @override
  void initState() {
    super.initState();
    _future = _loadCard();
  }

  void _reload() {
    setState(() {
      _future = _loadCard();
    });
  }

  Future<ProfileQrCardData> _loadCard() async {
    final card = await ref
        .read(profileEditQueryProvider(AppUiSurfaces.myQrCode))
        .getProfileQrCard();
    _validateCard(card);
    return card;
  }

  void _validateCard(ProfileQrCardData card) {
    final trustedPublicOrigin = ref
        .read(publicContentLinkBuilderProvider)
        .publicWebOrigin;
    card.requireUsableAt(
      trustedPublicOrigin: trustedPublicOrigin,
      now: (widget.clock ?? DateTime.now)(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
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
          ProfileText.editProfileQrCardTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: FutureBuilder<ProfileQrCardData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return AppPageErrorState(
              semantic: UiErrorSemanticResolver.resolve(
                context,
                error: snapshot.error!,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
              ),
              onRecovery: (action) async {
                if (action.type == UiErrorActionType.retry) {
                  _reload();
                  return UiRecoveryOutcome.superseded;
                }
                return UiRecoveryOutcome.cancelled;
              },
            );
          }
          if (!snapshot.hasData) {
            return AppRequestFeedback.section();
          }
          return MyQrCardView(
            card: snapshot.data!,
            sharePresenter: widget.sharePresenter,
            validateCard: _validateCard,
            onValidationRetry: _reload,
            onScanPressed: () {
              unawaited(
                ref
                    .read(journeyEventTrackerProvider)
                    .trackAction(
                      journey: 'contact_add',
                      action: 'open_scanner_from_my_qr',
                      pageName: 'MyQrCodePage',
                    ),
              );
              context.push(AppRoutePaths.addContactScan);
            },
          );
        },
      ),
    );
  }
}
