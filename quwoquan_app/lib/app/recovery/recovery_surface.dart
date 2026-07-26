import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/app/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/app/recovery/startup_recovery_controller.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

class StartupRecoveryPage extends StatefulWidget {
  const StartupRecoveryPage({super.key, this.controller});

  final StartupRecoveryController? controller;

  @override
  State<StartupRecoveryPage> createState() => _StartupRecoveryPageState();
}

class _StartupRecoveryPageState extends State<StartupRecoveryPage>
    with WidgetsBindingObserver {
  late final StartupRecoveryController _controller;
  late final bool _ownsController;

  @override
  void initState() {
    super.initState();
    _ownsController = widget.controller == null;
    _controller = widget.controller ?? StartupRecoveryController();
    WidgetsBinding.instance.addObserver(this);
    _controller.addListener(_onChanged);
    _controller.start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.removeListener(_onChanged);
    if (_ownsController) _controller.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _controller.refreshVersionAfterExternalReturn();
    }
  }

  void _onChanged() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = _controller.snapshot;
    const colors = AppColorsTheme(isDark: false);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColorsFunctional.getColor(
          false,
          ColorType.surfaceMuted,
        ),
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: AppScaffold(
        backgroundColor: AppColorsFunctional.getColor(
          false,
          ColorType.surfaceMuted,
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.recoveryHorizontalInset,
            ),
            child: Align(
              alignment: const Alignment(
                0,
                AppSpacing.recoveryVisualCenterAlignment,
              ),
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: AppSpacing.recoveryContentMaxWidth,
                ),
                child: Semantics(
                  container: true,
                  explicitChildNodes: true,
                  child: _RecoveryContent(
                    snapshot: snapshot,
                    colors: colors,
                    openingExternalTarget: _controller.openingExternalTarget,
                    onUpdate: _openUpdate,
                    onWeb: _openWeb,
                    onReenter: _controller.reenterRuntime,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _openUpdate() async {
    final opened = await _controller.openUpdate();
    if (!opened && mounted) {
      _showTransientMessage(UITextConstants.startupRecoveryUpdateOpenFailed);
    }
  }

  Future<void> _openWeb() async {
    final opened = await _controller.openWeb();
    if (!opened && mounted) {
      _showTransientMessage(UITextConstants.startupRecoveryWebOpenFailed);
    }
  }

  void _showTransientMessage(String message) {
    AppToast.show(context, message);
  }
}

class _RecoveryContent extends StatelessWidget {
  const _RecoveryContent({
    required this.snapshot,
    required this.colors,
    required this.openingExternalTarget,
    required this.onUpdate,
    required this.onWeb,
    required this.onReenter,
  });

  final RecoverySnapshot snapshot;
  final AppColorsTheme colors;
  final bool openingExternalTarget;
  final VoidCallback onUpdate;
  final VoidCallback onWeb;
  final VoidCallback onReenter;

  @override
  Widget build(BuildContext context) {
    final content = _copyFor(snapshot.phase);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        SizedBox(
          height: AppSpacing.recoveryTitleSlotHeight,
          child: Center(
            child: _AnimatedRecoveryText(
              key: ValueKey<String>('title-${snapshot.phase.name}'),
              text: content.title,
              style: TextStyle(
                color: colors.foregroundPrimary,
                fontSize: AppTypography.iosProfileTitle,
                fontWeight: AppTypography.semiBold,
                height: AppTypography.lineHeightTight,
              ),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.recoveryTitleSubtitleGap),
        SizedBox(
          height: AppSpacing.recoverySubtitleSlotHeight,
          child: Center(
            child: _AnimatedRecoveryText(
              key: ValueKey<String>('subtitle-${snapshot.phase.name}'),
              text: content.subtitle,
              style: TextStyle(
                color: colors.foregroundSecondary,
                fontSize: AppTypography.iosBody,
                fontWeight: AppTypography.regular,
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.recoverySubtitleActionGap),
        SizedBox(
          height: AppSpacing.recoveryActionSlotHeight,
          child: _RecoveryActions(
            snapshot: snapshot,
            openingExternalTarget: openingExternalTarget,
            onUpdate: onUpdate,
            onWeb: onWeb,
            onReenter: onReenter,
          ),
        ),
      ],
    );
  }
}

class _AnimatedRecoveryText extends StatelessWidget {
  const _AnimatedRecoveryText({
    super.key,
    required this.text,
    required this.style,
  });

  final String text;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: AppSpacing.recoveryNewContentFadeDuration,
      reverseDuration: AppSpacing.recoveryOldContentFadeDuration,
      transitionBuilder: (child, animation) =>
          FadeTransition(opacity: animation, child: child),
      child: Text(
        text,
        key: ValueKey<String>(text),
        textAlign: TextAlign.center,
        maxLines: 2,
        overflow: TextOverflow.visible,
        style: style,
      ),
    );
  }
}

class _RecoveryActions extends StatelessWidget {
  const _RecoveryActions({
    required this.snapshot,
    required this.openingExternalTarget,
    required this.onUpdate,
    required this.onWeb,
    required this.onReenter,
  });

  final RecoverySnapshot snapshot;
  final bool openingExternalTarget;
  final VoidCallback onUpdate;
  final VoidCallback onWeb;
  final VoidCallback onReenter;

  @override
  Widget build(BuildContext context) {
    final phase = snapshot.phase;
    final checking =
        phase == RecoveryPhase.startupChecking ||
        phase == RecoveryPhase.runtimeVersionChecking;
    final showsUpdate = snapshot.showsUpdate;
    final runtimeUnavailable = phase == RecoveryPhase.runtimeUnavailable;
    final runtimeReentering = phase == RecoveryPhase.runtimeReentering;
    final onlyWeb =
        phase == RecoveryPhase.startupLatest ||
        phase == RecoveryPhase.startupVersionUnavailable ||
        phase == RecoveryPhase.runtimeLatest ||
        phase == RecoveryPhase.runtimeVersionUnavailable;
    final primaryLabel = runtimeUnavailable
        ? UITextConstants.runtimeRecoveryAction
        : runtimeReentering
        ? UITextConstants.runtimeRecoveryEnteringAction
        : checking
        ? UITextConstants.startupRecoveryCheckingAction
        : showsUpdate
        ? UITextConstants.startupRecoveryUpdateAction
        : UITextConstants.startupRecoveryWebAction;
    final primaryAction = checking || runtimeReentering || openingExternalTarget
        ? null
        : runtimeUnavailable
        ? onReenter
        : showsUpdate
        ? onUpdate
        : onWeb;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _RecoveryButton(
          label: primaryLabel,
          onPressed: primaryAction,
          filled: true,
        ),
        if (!onlyWeb) ...<Widget>[
          const SizedBox(height: AppSpacing.recoveryButtonGap),
          _RecoveryButton(
            label: UITextConstants.startupRecoveryWebAction,
            onPressed: openingExternalTarget ? null : onWeb,
            filled: false,
          ),
        ],
      ],
    );
  }
}

class _RecoveryButton extends StatelessWidget {
  const _RecoveryButton({
    required this.label,
    required this.onPressed,
    required this.filled,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    const colors = AppColorsTheme(isDark: false);
    final style = ButtonStyle(
      minimumSize: const WidgetStatePropertyAll<Size>(
        Size.fromHeight(AppSpacing.buttonHeight),
      ),
      textStyle: const WidgetStatePropertyAll<TextStyle>(
        TextStyle(
          fontSize: AppTypography.iosBody,
          fontWeight: AppTypography.medium,
        ),
      ),
      shape: const WidgetStatePropertyAll<OutlinedBorder>(StadiumBorder()),
    );
    if (filled) {
      return SizedBox(
        width: double.infinity,
        child: FilledButton(
          style: style.copyWith(
            backgroundColor: WidgetStateProperty.resolveWith<Color>((states) {
              if (states.contains(WidgetState.disabled)) {
                return AppColorsFunctional.getColor(
                  false,
                  ColorType.pressedSurface,
                );
              }
              return AppColors.primaryColor;
            }),
            foregroundColor: WidgetStateProperty.resolveWith<Color>((states) {
              if (states.contains(WidgetState.disabled)) {
                return colors.foregroundSecondary;
              }
              return colors.foregroundInverse;
            }),
          ),
          onPressed: onPressed,
          child: Text(label),
        ),
      );
    }
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton(
        style: style.copyWith(
          foregroundColor: const WidgetStatePropertyAll<Color>(
            AppColors.primaryColor,
          ),
          side: const WidgetStatePropertyAll<BorderSide>(
            BorderSide(color: AppColors.primaryColor, width: AppSpacing.one),
          ),
        ),
        onPressed: onPressed,
        child: Text(label),
      ),
    );
  }
}

class _RecoveryCopy {
  const _RecoveryCopy(this.title, this.subtitle);

  final String title;
  final String subtitle;
}

_RecoveryCopy _copyFor(RecoveryPhase phase) {
  switch (phase) {
    case RecoveryPhase.startupChecking:
      return const _RecoveryCopy(
        UITextConstants.startupRecoveryTitle,
        UITextConstants.startupRecoveryChecking,
      );
    case RecoveryPhase.startupUpdateRequired:
      return const _RecoveryCopy(
        UITextConstants.startupRecoveryUpdateTitle,
        UITextConstants.startupRecoveryUpdateMessage,
      );
    case RecoveryPhase.startupLatest:
      return const _RecoveryCopy(
        UITextConstants.startupRecoveryLatestTitle,
        UITextConstants.startupRecoveryWebMessage,
      );
    case RecoveryPhase.startupVersionUnavailable:
      return const _RecoveryCopy(
        UITextConstants.startupRecoveryTitle,
        UITextConstants.startupRecoveryWebMessage,
      );
    case RecoveryPhase.runtimeUnavailable:
      return const _RecoveryCopy(
        UITextConstants.runtimeRecoveryTitle,
        UITextConstants.runtimeRecoveryMessage,
      );
    case RecoveryPhase.runtimeReentering:
      return const _RecoveryCopy(
        UITextConstants.runtimeRecoveryEnteringTitle,
        UITextConstants.runtimeRecoveryEnteringMessage,
      );
    case RecoveryPhase.runtimeVersionChecking:
      return const _RecoveryCopy(
        UITextConstants.runtimeRecoveryTitle,
        UITextConstants.startupRecoveryChecking,
      );
    case RecoveryPhase.runtimeUpdateRequired:
      return const _RecoveryCopy(
        UITextConstants.startupRecoveryUpdateTitle,
        UITextConstants.runtimeRecoveryUpdateMessage,
      );
    case RecoveryPhase.runtimeLatest:
      return const _RecoveryCopy(
        UITextConstants.startupRecoveryLatestTitle,
        UITextConstants.startupRecoveryWebMessage,
      );
    case RecoveryPhase.runtimeVersionUnavailable:
      return const _RecoveryCopy(
        UITextConstants.runtimeRecoveryTitle,
        UITextConstants.startupRecoveryWebMessage,
      );
  }
}
