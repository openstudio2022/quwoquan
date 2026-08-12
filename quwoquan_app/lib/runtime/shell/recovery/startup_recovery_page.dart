import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/recovery_surface_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/runtime/shell/recovery/startup_recovery_controller.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;

class StartupRecoveryPage extends StatefulWidget {
  const StartupRecoveryPage({
    super.key,
    required this.mount,
    this.controller,
    this.failureCode = '',
    this.failureSource = '',
  });

  const StartupRecoveryPage.routerError({
    super.key,
    this.controller,
    this.failureCode = '',
    this.failureSource = 'router',
  }) : mount = ops_contracts.StartupRecoveryMount.routerError;

  const StartupRecoveryPage.safeShell({
    super.key,
    this.controller,
    this.failureCode = '',
    this.failureSource = 'router',
  }) : mount = ops_contracts.StartupRecoveryMount.safeShell;

  final ops_contracts.StartupRecoveryMount mount;
  final StartupRecoveryController? controller;
  final String failureCode;
  final String failureSource;

  @override
  State<StartupRecoveryPage> createState() => _StartupRecoveryPageState();
}

class _StartupRecoveryPageState extends State<StartupRecoveryPage>
    with WidgetsBindingObserver {
  late final StartupRecoveryController _controller;
  late final bool _ownsController;
  late final RecoverySurfaceTelemetrySession _telemetry;
  late RecoveryPhase _lastPhase;
  bool _successfulExternalAction = false;

  @override
  void initState() {
    super.initState();
    _ownsController = widget.controller == null;
    _controller = widget.controller ?? StartupRecoveryController();
    _lastPhase = _controller.snapshot.phase;
    _telemetry = RecoverySurfaceTelemetrySession(
      mount: widget.mount,
      initialPhase: _telemetryPhase(_lastPhase),
      elapsedMs: () =>
          AppStartupRuntime.instance.elapsedSinceProcessStart.inMilliseconds,
      failureCode: widget.failureCode,
      failureSource: widget.failureSource,
    );
    WidgetsBinding.instance.addObserver(this);
    _controller.addListener(_onChanged);
    _controller.start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.removeListener(_onChanged);
    final runtimeReentryCompleting =
        _controller.snapshot.phase == RecoveryPhase.runtimeReentering;
    if (runtimeReentryCompleting) {
      _telemetry.runtimeReentry(outcome: 'success');
    }
    _telemetry.exit(
      outcome: runtimeReentryCompleting || _successfulExternalAction
          ? 'success'
          : 'failed',
    );
    if (_ownsController) _controller.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      if (_controller.refreshVersionAfterExternalReturn()) {
        _telemetry.externalAction(
          action: ops_contracts.StartupRecoveryAction.externalReturn,
          outcome: 'success',
        );
      }
    }
  }

  void _onChanged() {
    final nextPhase = _controller.snapshot.phase;
    if (_lastPhase == RecoveryPhase.runtimeReentering &&
        nextPhase == RecoveryPhase.runtimeVersionChecking) {
      _telemetry.runtimeReentry(outcome: 'failed');
      _telemetry.failure(failureSource: 'runtime_boundary');
    }
    _telemetry.phaseChanged(_telemetryPhase(nextPhase));
    _lastPhase = nextPhase;
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
              horizontal: RecoverySurfaceSpacing.horizontalInset,
            ),
            child: Align(
              alignment: const Alignment(
                0,
                RecoverySurfaceSpacing.visualCenterAlignment,
              ),
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: RecoverySurfaceSpacing.contentMaxWidth,
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
                    onReenter: _reenterRuntime,
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
    _telemetry.externalAction(
      action: ops_contracts.StartupRecoveryAction.openUpdate,
      outcome: 'started',
    );
    final opened = await _controller.openUpdate();
    _telemetry.externalAction(
      action: ops_contracts.StartupRecoveryAction.openUpdate,
      outcome: opened ? 'success' : 'failed',
    );
    _successfulExternalAction |= opened;
    if (!opened && mounted) {
      _showTransientMessage(FoundationText.startupRecoveryUpdateOpenFailed);
    }
  }

  Future<void> _openWeb() async {
    _telemetry.externalAction(
      action: ops_contracts.StartupRecoveryAction.openWeb,
      outcome: 'started',
    );
    final opened = await _controller.openWeb();
    _telemetry.externalAction(
      action: ops_contracts.StartupRecoveryAction.openWeb,
      outcome: opened ? 'success' : 'failed',
    );
    _successfulExternalAction |= opened;
    if (!opened && mounted) {
      _showTransientMessage(FoundationText.startupRecoveryWebOpenFailed);
    }
  }

  Future<void> _reenterRuntime() async {
    _telemetry.runtimeReentry(outcome: 'started');
    await _controller.reenterRuntime();
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
    final content = _copyFor(snapshot);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        SizedBox(
          height: RecoverySurfaceSpacing.titleSlotHeight,
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
        const SizedBox(height: RecoverySurfaceSpacing.titleSubtitleGap),
        SizedBox(
          height: RecoverySurfaceSpacing.subtitleSlotHeight,
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
        const SizedBox(height: RecoverySurfaceSpacing.subtitleActionGap),
        SizedBox(
          height: RecoverySurfaceSpacing.actionSlotHeight,
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
      duration: RecoverySurfaceSpacing.newContentFadeDuration,
      reverseDuration: RecoverySurfaceSpacing.oldContentFadeDuration,
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
        ? FoundationText.runtimeRecoveryAction
        : runtimeReentering
        ? FoundationText.runtimeRecoveryEnteringAction
        : checking
        ? FoundationText.startupRecoveryCheckingAction
        : showsUpdate
        ? FoundationText.startupRecoveryUpdateAction
        : FoundationText.startupRecoveryWebAction;
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
          const SizedBox(height: RecoverySurfaceSpacing.buttonGap),
          _RecoveryButton(
            label: FoundationText.startupRecoveryWebAction,
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

_RecoveryCopy _copyFor(RecoverySnapshot snapshot) {
  final phase = snapshot.phase;
  switch (phase) {
    case RecoveryPhase.startupChecking:
      return const _RecoveryCopy(
        FoundationText.startupRecoveryTitle,
        FoundationText.startupRecoveryChecking,
      );
    case RecoveryPhase.startupUpdateRequired:
      return snapshot.requiresUpdate
          ? const _RecoveryCopy(
              FoundationText.startupRecoveryUpdateTitle,
              FoundationText.startupRecoveryUpdateMessage,
            )
          : const _RecoveryCopy(
              FoundationText.startupRecoveryUpdateAvailableTitle,
              FoundationText.startupRecoveryUpdateAvailableMessage,
            );
    case RecoveryPhase.startupLatest:
      return const _RecoveryCopy(
        FoundationText.startupRecoveryLatestTitle,
        FoundationText.startupRecoveryWebMessage,
      );
    case RecoveryPhase.startupVersionUnavailable:
      return const _RecoveryCopy(
        FoundationText.startupRecoveryTitle,
        FoundationText.startupRecoveryWebMessage,
      );
    case RecoveryPhase.runtimeUnavailable:
      return const _RecoveryCopy(
        FoundationText.runtimeRecoveryTitle,
        FoundationText.runtimeRecoveryMessage,
      );
    case RecoveryPhase.runtimeReentering:
      return const _RecoveryCopy(
        FoundationText.runtimeRecoveryEnteringTitle,
        FoundationText.runtimeRecoveryEnteringMessage,
      );
    case RecoveryPhase.runtimeVersionChecking:
      return const _RecoveryCopy(
        FoundationText.runtimeRecoveryTitle,
        FoundationText.startupRecoveryChecking,
      );
    case RecoveryPhase.runtimeUpdateRequired:
      return snapshot.requiresUpdate
          ? const _RecoveryCopy(
              FoundationText.startupRecoveryUpdateTitle,
              FoundationText.runtimeRecoveryUpdateMessage,
            )
          : const _RecoveryCopy(
              FoundationText.startupRecoveryUpdateAvailableTitle,
              FoundationText.runtimeRecoveryUpdateAvailableMessage,
            );
    case RecoveryPhase.runtimeLatest:
      return const _RecoveryCopy(
        FoundationText.startupRecoveryLatestTitle,
        FoundationText.startupRecoveryWebMessage,
      );
    case RecoveryPhase.runtimeVersionUnavailable:
      return const _RecoveryCopy(
        FoundationText.runtimeRecoveryTitle,
        FoundationText.startupRecoveryWebMessage,
      );
  }
}

ops_contracts.StartupRecoveryPhase _telemetryPhase(RecoveryPhase phase) {
  return switch (phase) {
    RecoveryPhase.startupChecking =>
      ops_contracts.StartupRecoveryPhase.startupChecking,
    RecoveryPhase.startupUpdateRequired =>
      ops_contracts.StartupRecoveryPhase.startupUpdateRequired,
    RecoveryPhase.startupLatest =>
      ops_contracts.StartupRecoveryPhase.startupLatest,
    RecoveryPhase.startupVersionUnavailable =>
      ops_contracts.StartupRecoveryPhase.startupVersionUnavailable,
    RecoveryPhase.runtimeUnavailable =>
      ops_contracts.StartupRecoveryPhase.runtimeUnavailable,
    RecoveryPhase.runtimeReentering =>
      ops_contracts.StartupRecoveryPhase.runtimeReentering,
    RecoveryPhase.runtimeVersionChecking =>
      ops_contracts.StartupRecoveryPhase.runtimeVersionChecking,
    RecoveryPhase.runtimeUpdateRequired =>
      ops_contracts.StartupRecoveryPhase.runtimeUpdateRequired,
    RecoveryPhase.runtimeLatest =>
      ops_contracts.StartupRecoveryPhase.runtimeLatest,
    RecoveryPhase.runtimeVersionUnavailable =>
      ops_contracts.StartupRecoveryPhase.runtimeVersionUnavailable,
  };
}
