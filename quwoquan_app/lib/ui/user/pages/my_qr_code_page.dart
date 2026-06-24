import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/widgets/my_qr_card.dart';

/// 我的二维码独立页：复用 [MyQrCardView]，扫一扫按钮跳转扫码页。
class MyQrCodePage extends ConsumerStatefulWidget {
  const MyQrCodePage({super.key});

  @override
  ConsumerState<MyQrCodePage> createState() => _MyQrCodePageState();
}

class _MyQrCodePageState extends ConsumerState<MyQrCodePage> {
  late Future<ProfileQrCardData> _future;

  @override
  void initState() {
    super.initState();
    _future = ref.read(userProfileRepositoryProvider).getProfileQrCard();
  }

  void _reload() {
    setState(() {
      _future = ref.read(userProfileRepositoryProvider).getProfileQrCard();
    });
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
          UITextConstants.editProfileQrCardTitle,
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
              onAction: (action) async {
                if (action.type == UiErrorActionType.retry) {
                  _reload();
                }
              },
            );
          }
          if (!snapshot.hasData) {
            return const Center(child: CupertinoActivityIndicator());
          }
          return MyQrCardView(
            card: snapshot.data!,
            onScanPressed: () => context.push(AppRoutePaths.addContactScan),
          );
        },
      ),
    );
  }
}
