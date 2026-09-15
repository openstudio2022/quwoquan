import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

/// 非电话本地确认表单；不读取环境，不调用短信、AutoFill或Remote登录。
class SyntheticLoginForm extends ConsumerStatefulWidget {
  const SyntheticLoginForm({
    super.key,
    required this.capability,
    required this.onCompleted,
    required this.onCancelled,
  });
  final SyntheticLoginCapability capability;
  final VoidCallback onCompleted;
  final VoidCallback onCancelled;
  @override
  ConsumerState<SyntheticLoginForm> createState() => _SyntheticLoginFormState();
}

class _SyntheticLoginFormState extends ConsumerState<SyntheticLoginForm> {
  final _identity = TextEditingController();
  final _confirmation = TextEditingController();
  late final AuthSessionController _auth;
  late final void Function() _requireIntent;
  SyntheticChallengeView? _challenge;
  BeginSyntheticChallenge? _begin;
  CompleteSyntheticChallenge? _complete;
  SyntheticSessionResult? _committedResult;
  bool _busy = false;
  bool _terminal = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _auth = ref.read(authSessionControllerProvider.notifier);
    _requireIntent = _auth.beginSyntheticLoginIntent();
    try {
      _check();
      _identity.text = widget.capability.createIdentityLabel().value;
    } catch (_) {
      _error = FoundationText.syntheticLoginUnavailable;
    }
  }

  void _check() {
    if (!mounted || _terminal) throw StateError('cancelled synthetic intent');
    widget.capability.requireCurrent();
    _requireIntent();
  }

  void _cancel() {
    if (_terminal) return;
    setState(() {
      _terminal = true;
      _busy = false;
    });
    _auth.cancelSyntheticLoginIntent();
    widget.onCancelled();
  }

  @override
  void dispose() {
    if (!_terminal) _auth.cancelSyntheticLoginIntent();
    _terminal = true;
    _identity.dispose();
    _confirmation.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || _terminal) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      _check();
      if (_challenge == null) {
        _begin ??= BeginSyntheticChallenge(
          identity: SyntheticIdentityLabel(value: _identity.text),
          requestKey: widget.capability.createRequestKey(),
        );
        final challenge = await widget.capability.challengePort.begin(_begin!);
        _check();
        setState(() {
          _challenge = challenge;
        });
      } else {
        _complete ??= CompleteSyntheticChallenge(
          identityLabel: _begin!.identity.value,
          challengeId: _challenge!.challengeId,
          confirmationHint: _confirmation.text,
          requestKey: widget.capability.createRequestKey(),
        );
        // 两次提交非跨库事务。第一步成功后只重试原意图，不重新begin或生成request。
        final result = await widget.capability.sessionPort.complete(_complete!);
        _check();
        _committedResult = result;
        await _auth.applySyntheticSession(result, requireIntent: _check);
        _check();
        setState(() {
          _terminal = true;
          _busy = false;
        });
        widget.onCompleted();
      }
    } on ArgumentError {
      if (mounted && !_terminal) {
        setState(() {
          _error = FoundationText.syntheticLoginInvalid;
        });
      }
    } on SyntheticLoginFailure catch (failure) {
      if (mounted && !_terminal) {
        setState(() {
          _error = switch (failure.reason) {
            SyntheticLoginFailureReason.mismatch =>
              FoundationText.syntheticLoginMismatch,
            SyntheticLoginFailureReason.invalidinput =>
              FoundationText.syntheticLoginInvalid,
            SyntheticLoginFailureReason.storageunavailable =>
              FoundationText.syntheticLoginStorageFailed,
            _ => FoundationText.syntheticLoginUnavailable,
          };
          if (failure.reason == SyntheticLoginFailureReason.mismatch) {
            _complete = null;
          }
        });
      }
    } catch (_) {
      if (mounted && !_terminal) {
        setState(() {
          _error = _committedResult != null
              ? FoundationText.syntheticLoginStorageFailed
              : FoundationText.syntheticLoginUnavailable;
        });
      }
    } finally {
      if (mounted && !_terminal) {
        setState(() {
          _busy = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    onPopInvokedWithResult: (didPop, _) {
      if (!didPop) _cancel();
    },
    child: SafeArea(
      child: Column(
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: CupertinoButton(
              key: const ValueKey('syntheticLoginBack'),
              onPressed: _cancel,
              child: const Icon(CupertinoIcons.back),
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Column(
                children: [
                  Text(
                    FoundationText.syntheticLoginTitle,
                    style: TextStyle(
                      fontSize: AppTypography.xl,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  const Text(
                    FoundationText.syntheticLoginExplanation,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  CupertinoTextField(
                    key: const ValueKey('syntheticLoginIdentity'),
                    controller: _identity,
                    readOnly: _challenge != null || _busy,
                    placeholder: FoundationText.syntheticLoginIdentity,
                    autocorrect: false,
                    enableSuggestions: false,
                    autofillHints: const [],
                    onChanged: (_) {
                      _begin = null;
                    },
                  ),
                  if (_challenge case final challenge?) ...[
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      challenge.confirmationHint,
                      key: const ValueKey('syntheticLoginHint'),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    CupertinoTextField(
                      key: const ValueKey('syntheticLoginConfirmation'),
                      controller: _confirmation,
                      readOnly: _busy || _committedResult != null,
                      placeholder: FoundationText.syntheticLoginConfirmation,
                      autocorrect: false,
                      enableSuggestions: false,
                      autofillHints: const [],
                      onChanged: (_) {
                        if (_committedResult == null) _complete = null;
                      },
                    ),
                  ],
                  const SizedBox(height: AppSpacing.md),
                  if (_error case final error?)
                    Text(
                      error,
                      key: const ValueKey('syntheticLoginError'),
                      style: TextStyle(
                        color: AppColors.errorForeground(context),
                      ),
                    ),
                  const SizedBox(height: AppSpacing.md),
                  CupertinoButton(
                    key: const ValueKey('syntheticLoginSubmit'),
                    onPressed: _busy || _terminal ? null : _submit,
                    child: _busy
                        ? const CupertinoActivityIndicator()
                        : Text(
                            _challenge == null
                                ? FoundationText.syntheticLoginBegin
                                : _committedResult == null
                                ? FoundationText.syntheticLoginConfirm
                                : FoundationText.syntheticLoginRetry,
                          ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    ),
  );
}
