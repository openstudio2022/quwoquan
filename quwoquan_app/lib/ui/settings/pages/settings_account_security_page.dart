import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/application/user/account/account_closure_local_data_purger_provider.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/auth/terminal_account_cleanup_receipt_store.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class SettingsAccountSecurityPage extends ConsumerStatefulWidget {
  const SettingsAccountSecurityPage({super.key});

  @override
  ConsumerState<SettingsAccountSecurityPage> createState() =>
      _SettingsAccountSecurityPageState();
}

class _SettingsAccountSecurityPageState
    extends ConsumerState<SettingsAccountSecurityPage> {
  late Future<ListCredentialsSlice> _credentials;
  bool _closingAccount = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    _credentials = ref
        .read(credentialBindingQueryProvider)
        .listCredentials(ListCredentialsQuery());
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: SettingsText.settingsAccountSecurity,
      onBack: () => _goBack(context),
      body: WebPageMaxWidthFrame(
        child: SafeArea(
          bottom: false,
          child: FutureBuilder<ListCredentialsSlice>(
            future: _credentials,
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
                      setState(_reload);
                      return UiRecoveryOutcome.superseded;
                    }
                    return UiRecoveryOutcome.cancelled;
                  },
                );
              }
              if (!snapshot.hasData) {
                return AppRequestFeedback.section();
              }
              return _buildCredentials(
                isDark,
                snapshot.data!.credentials
                    .where((item) => item.isActive)
                    .toList(),
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildCredentials(bool isDark, List<CredentialBindingView> items) {
    return ListView(
      padding: EdgeInsets.only(
        left: SettingsSemanticConstants.insetFormListHorizontalPadding,
        right: SettingsSemanticConstants.insetFormListHorizontalPadding,
        top: AppSpacing.intraGroupSm,
        bottom: AppSpacing.xl,
      ),
      children: <Widget>[
        SettingsInsetGroupedSection(
          isDark: isDark,
          header: SettingsText.settingsCredentialSection,
          child: items.isEmpty
              ? SettingsInsetFormRow(
                  isDark: isDark,
                  label: SettingsText.settingsCredentialEmpty,
                  trailing: const SizedBox.shrink(),
                )
              : Column(
                  children: <Widget>[
                    for (var index = 0; index < items.length; index++) ...[
                      SettingsInsetNavigationRow(
                        isDark: isDark,
                        label: _credentialLabel(
                          items[index].credentialType.wireName,
                        ),
                        trailingText:
                            items[index].displayLabel ??
                            SettingsText.settingsCredentialBound,
                        isDestructive: true,
                        showChevron: false,
                        onTap: () => unawaited(_confirmUnbind(items[index])),
                      ),
                      if (index + 1 < items.length)
                        SettingsInsetFormSectionDivider(isDark: isDark),
                    ],
                  ],
                ),
        ),
        SizedBox(height: SettingsSemanticConstants.insetFormSectionVerticalGap),
        SettingsInsetGroupedSection(
          isDark: isDark,
          child: SettingsInsetNavigationRow(
            isDark: isDark,
            label: SettingsText.settingsCredentialBindPhone,
            onTap: () => context.push(AppRoutePaths.profileEdit),
          ),
        ),
        SizedBox(height: SettingsSemanticConstants.insetFormSectionVerticalGap),
        SettingsInsetGroupedSection(
          isDark: isDark,
          header: SettingsText.settingsCloseAccountSection,
          child: SettingsInsetNavigationRow(
            isDark: isDark,
            label: SettingsText.settingsCloseAccountEntry,
            isDestructive: true,
            showChevron: false,
            trailing: _closingAccount ? AppRequestFeedback.inline() : null,
            onTap: _closingAccount
                ? null
                : () => unawaited(_confirmCloseAccount()),
          ),
        ),
      ],
    );
  }

  /// Apple 5.1.1(v)：App 内自助注销。确认对话必须完整说明删除范围与时限；
  /// 成功后本地会话清理并回登录安全态。
  Future<void> _confirmCloseAccount() async {
    if (_closingAccount) return;
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(SettingsText.settingsCloseAccountConfirmTitle),
        content: const Text(SettingsText.settingsCloseAccountConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(SettingsText.settingsCloseAccountConfirmAction),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _closingAccount = true;
    });
    try {
      await ref
          .read(accountLifecycleCommandWriterProvider)
          .closeAccount(CloseAccountCommand());
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _closingAccount = false;
      });
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
          allowRetry: false,
          presentation: UiErrorPresentation.actionDialog,
        ),
      );
      return;
    }

    final closureActor = AccountClosureLocalActorContext.fromSession(
      ref.read(authSessionControllerProvider),
    );
    final cleanupReceiptStore = ref.read(
      terminalAccountCleanupReceiptStoreProvider,
    );
    var cleanupReceiptPersisted = false;
    try {
      await cleanupReceiptStore.save(
        TerminalAccountCleanupReceipt(
          accountId: closureActor.accountId,
          personaId: closureActor.personaId,
          installId: closureActor.installId,
        ),
      );
      cleanupReceiptPersisted = true;
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'account_closure_local_cleanup_receipt',
          error: error,
          stackTrace: stackTrace,
          operationId: AppCloudOperationIds.userUserAccountCloseAccount,
        ),
      );
    }
    final sessionController = ref.read(authSessionControllerProvider.notifier);
    final localDataPurger = ref.read(accountClosureLocalDataPurgerProvider);
    try {
      await sessionController.hardLogout();
    } catch (error, stackTrace) {
      sessionController.forceGuestAfterTerminalAccountClosure();
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'account_closure_local_session_cleanup',
          error: error,
          stackTrace: stackTrace,
          operationId: AppCloudOperationIds.userUserAccountCloseAccount,
        ),
      );
    }
    try {
      await localDataPurger.purge();
      if (cleanupReceiptPersisted) {
        await cleanupReceiptStore.clear();
      }
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'account_closure_local_privacy_cleanup',
          error: error,
          stackTrace: stackTrace,
          operationId: AppCloudOperationIds.userUserAccountCloseAccount,
        ),
      );
      if (cleanupReceiptPersisted) {
        unawaited(ref.read(accountClosureLocalCleanupRecoveryProvider)());
      }
    }

    if (!mounted) return;
    AppToast.show(context, SettingsText.settingsCloseAccountDoneToast);
    context.go(AppRoutePaths.home);
  }

  Future<void> _confirmUnbind(CredentialBindingView credential) async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(SettingsText.settingsCredentialUnbindConfirmTitle),
        content: const Text(
          SettingsText.settingsCredentialUnbindConfirmMessage,
        ),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(SettingsText.settingsCredentialUnbind),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await ref
          .read(appCredentialBindingCommandWriterProvider)
          .unbindCredential(
            UnbindCredentialCommand(
              credentialType: credential.credentialType.wireName,
            ),
          );
      if (!mounted) return;
      setState(_reload);
    } catch (error) {
      if (!mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.backgroundAction,
          scope: UiErrorScope.dialog,
          allowRetry: false,
          presentation: UiErrorPresentation.actionDialog,
        ),
      );
    }
  }

  String _credentialLabel(String type) => switch (type) {
    'phone' => SettingsText.settingsCredentialPhone,
    'carrier_phone' => SettingsText.settingsCredentialCarrierPhone,
    _ => type,
  };

  void _goBack(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoutePaths.settings);
    }
  }
}
