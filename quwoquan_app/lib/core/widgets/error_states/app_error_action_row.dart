part of 'app_error_states.dart';

class _ErrorActionRow extends StatefulWidget {
  const _ErrorActionRow({
    required this.semantic,
    this.onAction,
    this.compact = false,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final bool compact;

  @override
  State<_ErrorActionRow> createState() => _ErrorActionRowState();
}

class _ErrorActionRowState extends State<_ErrorActionRow> {
  Timer? _countdown;
  late int _remainingSeconds;
  bool _dispatching = false;

  UiErrorSemantic get semantic => widget.semantic;
  UiErrorActionCallback? get onAction => widget.onAction;
  bool get compact => widget.compact;

  @override
  void initState() {
    super.initState();
    _startCountdown();
  }

  @override
  void didUpdateWidget(covariant _ErrorActionRow oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.semantic.primaryAction?.availableAfterSeconds !=
        widget.semantic.primaryAction?.availableAfterSeconds) {
      _startCountdown();
    }
  }

  void _startCountdown() {
    _countdown?.cancel();
    _remainingSeconds =
        widget.semantic.primaryAction?.availableAfterSeconds ?? 0;
    if (_remainingSeconds <= 0) return;
    _countdown = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _remainingSeconds <= 1) {
        timer.cancel();
        if (mounted) setState(() => _remainingSeconds = 0);
        return;
      }
      setState(() => _remainingSeconds--);
    });
  }

  @override
  void dispose() {
    _countdown?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (onAction == null) {
      return const SizedBox.shrink();
    }
    final actions = <Widget>[
      if (semantic.secondaryAction != null)
        _buildSecondaryAction(context, semantic.secondaryAction!),
      if (semantic.primaryAction != null)
        _buildPrimaryAction(context, semantic.primaryAction!),
    ];
    if (!compact) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: actions
            .map(
              (action) => Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.intraGroupXs,
                ),
                child: SizedBox(
                  width: AppSpacing.minInteractiveSize * 2.55,
                  height: AppSpacing.minInteractiveSize,
                  child: action,
                ),
              ),
            )
            .toList(growable: false),
      );
    }
    return Wrap(
      alignment: WrapAlignment.start,
      spacing: AppSpacing.containerSm,
      runSpacing: AppSpacing.containerSm,
      children: actions,
    );
  }

  Widget _buildSecondaryAction(BuildContext context, UiErrorAction action) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = isDark
        ? AppColors.white.withValues(alpha: 0.08)
        : CupertinoColors.systemBackground.resolveFrom(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.26 : 0.2);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        border: Border.all(color: border, width: AppSpacing.hairline),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? AppSpacing.sm : AppSpacing.containerMd,
          vertical: compact ? AppSpacing.xs : AppSpacing.sm,
        ),
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        onPressed: _canDispatch(action)
            ? () => unawaited(_dispatchAction(context, action))
            : null,
        child: Center(
          child: Text(
            action.label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: AppColors.iosLabel(context),
              fontWeight: AppTypography.medium,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPrimaryAction(BuildContext context, UiErrorAction action) {
    final waiting = _remainingSeconds > 0;
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? AppSpacing.containerSm : AppSpacing.containerMd,
        vertical: compact ? AppSpacing.xs : AppSpacing.sm,
      ),
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      color: AppColors.iosTintedFill(context),
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      onPressed: !waiting && !_dispatching && _canDispatch(action)
          ? () => unawaited(_dispatchAction(context, action))
          : null,
      child: Center(
        child: _dispatching
            ? CupertinoActivityIndicator(color: AppColors.iosAccent(context))
            : Text(
                waiting
                    ? SearchText.recoveryCountdownLabel(_remainingSeconds)
                    : action.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.iosAccent(context),
                  fontWeight: AppTypography.semiBold,
                ),
              ),
      ),
    );
  }

  Future<void> _dispatchAction(
    BuildContext context,
    UiErrorAction action,
  ) async {
    if (onAction == null) {
      return;
    }
    setState(() => _dispatching = true);
    try {
      await onAction!(action);
    } finally {
      if (mounted) setState(() => _dispatching = false);
    }
  }

  bool _canDispatch(UiErrorAction action) {
    return onAction != null;
  }
}
