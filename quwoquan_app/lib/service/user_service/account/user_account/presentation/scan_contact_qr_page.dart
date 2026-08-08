import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/image_pick_source.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/contact_qr_image_analyzer.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/domain/qr_payload_parser.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ProfileQrResolveWire;

/// 扫一扫页：全屏相机预览 + 取景框 + 扫描线动画 + 图库识别 + 我的二维码入口。
class ScanContactQrPage extends ConsumerStatefulWidget {
  const ScanContactQrPage({super.key});

  @override
  ConsumerState<ScanContactQrPage> createState() => _ScanContactQrPageState();
}

class _ScanContactQrPageState extends ConsumerState<ScanContactQrPage>
    with SingleTickerProviderStateMixin {
  MobileScannerController? _controller;
  late final AnimationController _scanLine;
  bool _handling = false;
  late bool _canUseCamera;
  late bool _canUseGallery;
  int _attemptGeneration = 0;
  int? _activeAttempt;

  @override
  void initState() {
    super.initState();
    _scanLine = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat();
    final caps = ref.read(platformCapabilitiesProvider);
    _canUseCamera = caps.camera;
    _canUseGallery = caps.mediaLibrary;
    if (_canUseCamera) {
      _controller = MobileScannerController();
    }
  }

  @override
  void dispose() {
    _attemptGeneration += 1;
    _activeAttempt = null;
    _scanLine.dispose();
    unawaited(_controller?.dispose());
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (capture.barcodes.isEmpty) {
      return;
    }
    final raw = capture.barcodes.first.rawValue?.trim() ?? '';
    await _startRawAttempt(raw);
  }

  Future<void> _pickFromGallery() async {
    if (!_canUseGallery) {
      return;
    }
    final attempt = _beginAttempt();
    if (attempt == null) {
      return;
    }
    try {
      final path = await ref
          .read(imagePickGatewayProvider)
          .pickImage(
            context,
            source: ImagePickSource.photoLibrary,
            cameraRouteName: PageAccessInternalRoutes.addContactScanGallery,
            galleryRouteName: PageAccessInternalRoutes.addContactScanGallery,
          );
      if (!mounted || !_isCurrentAttempt(attempt)) {
        return;
      }
      if (path == null || path.trim().isEmpty) {
        await _recoverAttempt(attempt);
        return;
      }
      final raw = await ref
          .read(contactQrImageAnalyzerProvider)
          .analyzeImage(path: path);
      if (!mounted || !_isCurrentAttempt(attempt)) {
        return;
      }
      if (raw.isEmpty) {
        AppToast.show(context, ContactText.scanQrNoCodeFound);
        await _recoverAttempt(attempt);
        return;
      }
      await _process(raw, attempt: attempt);
    } catch (error) {
      await _showAttemptError(
        attempt: attempt,
        error: error,
        retry: _pickFromGallery,
      );
    }
  }

  Future<void> _startRawAttempt(String raw) async {
    final attempt = _beginAttempt();
    if (attempt == null) {
      return;
    }
    await _process(raw, attempt: attempt);
  }

  Future<void> _process(String raw, {required int attempt}) async {
    if (!_isCurrentAttempt(attempt)) {
      return;
    }
    final trustedPublicOrigin = Uri.tryParse(
      CloudRuntimeConfig.publicWebBaseUrl.trim(),
    );
    final parsed = trustedPublicOrigin == null
        ? null
        : QrPayloadParser.parse(raw, trustedPublicOrigin: trustedPublicOrigin);
    if (parsed == null || !parsed.isValid) {
      if (_isCurrentAttempt(attempt)) {
        AppToast.show(context, ContactText.scanQrInvalidCode);
      }
      await _recoverAttempt(attempt);
      return;
    }
    try {
      final ProfileQrResolveWire resolved = await ref
          .read(profileEditQueryProvider(AppUiSurfaces.addContactScan))
          .resolveProfileQrToken(token: parsed.token, handle: parsed.handle);
      if (!mounted || !_isCurrentAttempt(attempt)) {
        return;
      }
      if (!_isAcceptedResolution(resolved, parsed)) {
        throw StateError('Profile QR resolution is not canonical');
      }
      final personaId = resolved.personaId.trim();
      final userHandle = resolved.userHandle.trim();
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'contact_discovery',
              action: 'resolve_profile_qr',
              pageName: 'ScanContactQrPage',
              targetType: 'user',
              targetKey: personaId,
            ),
      );
      context.pushReplacement(
        AppRoutePaths.addContactConfirm(
          handle: userHandle,
          userId: personaId,
          source: 'scan',
        ),
      );
    } catch (error) {
      await _showAttemptError(
        attempt: attempt,
        error: error,
        retry: () => _startRawAttempt(raw),
      );
    }
  }

  int? _beginAttempt() {
    if (!mounted || _handling || _activeAttempt != null) {
      return null;
    }
    final attempt = ++_attemptGeneration;
    setState(() {
      _handling = true;
      _activeAttempt = attempt;
    });
    unawaited(_controller?.stop());
    return attempt;
  }

  bool _isCurrentAttempt(int attempt) {
    return mounted && _handling && _activeAttempt == attempt;
  }

  bool _releaseAttempt(int attempt) {
    if (!_isCurrentAttempt(attempt)) {
      return false;
    }
    setState(() {
      _handling = false;
      _activeAttempt = null;
    });
    return true;
  }

  Future<void> _recoverAttempt(int attempt) async {
    if (!_releaseAttempt(attempt)) {
      return;
    }
    await _restartScanner();
  }

  Future<void> _restartScanner() async {
    final controller = _controller;
    if (!mounted || !_canUseCamera || controller == null) {
      return;
    }
    try {
      await controller.start();
    } catch (_) {
      if (mounted) {
        setState(() => _canUseCamera = false);
      }
    }
  }

  Future<void> _showAttemptError({
    required int attempt,
    required Object error,
    required Future<void> Function() retry,
  }) async {
    if (!_releaseAttempt(attempt) || !mounted) {
      return;
    }
    var retried = false;
    await AppActionErrorFeedback.show(
      context,
      semantic: ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
      ),
      onAction: (action) async {
        if ((action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) &&
            mounted &&
            _activeAttempt == null) {
          retried = true;
          await retry();
        }
      },
    );
    if (!retried && mounted && _activeAttempt == null) {
      await _restartScanner();
    }
  }

  bool _isAcceptedResolution(
    ProfileQrResolveWire resolved,
    QrPayloadParseResult parsed,
  ) {
    final personaId = resolved.personaId.trim();
    final userHandle = resolved.userHandle.trim();
    final publicProfileUrl = resolved.publicProfileUrl.trim();
    return personaId.isNotEmpty &&
        personaId == resolved.personaId &&
        resolved.scanStatus == 'accepted' &&
        userHandle == resolved.userHandle &&
        userHandle == parsed.handle &&
        publicProfileUrl == resolved.publicProfileUrl &&
        publicProfileUrl == parsed.publicProfileUrl;
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return CupertinoPageScaffold(
      backgroundColor: AppColors.black,
      child: DefaultTextStyle(
        style: const TextStyle(decoration: TextDecoration.none),
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            if (_canUseCamera && controller != null)
              MobileScanner(
                controller: controller,
                onDetect: _onDetect,
                errorBuilder: (_, _) => const _CameraUnavailable(),
                placeholderBuilder: (_) =>
                    const ColoredBox(color: AppColors.black),
              )
            else
              const _CameraUnavailable(),
            if (_canUseCamera && controller != null)
              _ScannerOverlay(animation: _scanLine),
            SafeArea(
              child: Column(
                children: <Widget>[
                  _TopBar(onClose: _close),
                  const Spacer(),
                  Padding(
                    padding: EdgeInsets.only(bottom: AppSpacing.containerXl),
                    child: Text(
                      ContactText.scanQrHint,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.white,
                      ),
                    ),
                  ),
                  Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerXl,
                      vertical: AppSpacing.containerMd,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: <Widget>[
                        _CircleAction(
                          icon: CupertinoIcons.qrcode,
                          label: ProfileText.editProfileQrCardTitle,
                          onTap: () => context.push(AppRoutePaths.myQrCode),
                        ),
                        if (_canUseGallery)
                          _CircleAction(
                            icon: CupertinoIcons.photo,
                            label: ContactText.scanQrAlbum,
                            onTap: () => unawaited(_pickFromGallery()),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _close() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoutePaths.addContact);
    }
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.onClose});

  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: Row(
        children: <Widget>[
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
            onPressed: onClose,
            child: Icon(
              CupertinoIcons.xmark,
              color: AppColors.white,
              size: AppSpacing.iconMedium,
            ),
          ),
        ],
      ),
    );
  }
}

class _CircleAction extends StatelessWidget {
  const _CircleAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            width: AppSpacing.iconButtonMinSizeSm,
            height: AppSpacing.iconButtonMinSizeSm,
            decoration: BoxDecoration(
              color: AppColors.white.withValues(alpha: 0.16),
              shape: BoxShape.circle,
            ),
            alignment: Alignment.center,
            child: Icon(
              icon,
              color: AppColors.white,
              size: AppSpacing.iconMedium,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.white,
            ),
          ),
        ],
      ),
    );
  }
}

class _ScannerOverlay extends StatelessWidget {
  const _ScannerOverlay({required this.animation});

  final Animation<double> animation;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    const double frameSize = 248;
    return Center(
      child: SizedBox(
        width: frameSize,
        height: frameSize,
        child: Stack(
          children: <Widget>[
            DecoratedBox(
              decoration: BoxDecoration(
                border: Border.all(color: accent, width: AppSpacing.two),
                borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
              ),
            ),
            AnimatedBuilder(
              animation: animation,
              builder: (context, _) {
                final top = animation.value * (frameSize - AppSpacing.two);
                return Positioned(
                  top: top,
                  left: AppSpacing.containerMd,
                  right: AppSpacing.containerMd,
                  child: Container(
                    height: AppSpacing.two,
                    decoration: BoxDecoration(
                      color: accent,
                      borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _CameraUnavailable extends StatelessWidget {
  const _CameraUnavailable();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerXl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: AppSpacing.avatarUserLg,
              height: AppSpacing.avatarUserLg,
              decoration: BoxDecoration(
                color: AppColors.white.withValues(alpha: 0.14),
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: Icon(
                CupertinoIcons.camera,
                color: AppColors.white,
                size: AppSpacing.iconMedium,
              ),
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              ContactText.scanQrCameraUnavailableTitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.white,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              ContactText.scanQrCameraUnavailableBody,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCallout,
                height: AppSpacing.textLineHeightBody,
                color: AppColors.white.withValues(alpha: 0.78),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
