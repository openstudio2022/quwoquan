import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

@immutable
class CameraCaptureResult {
  const CameraCaptureResult({
    required this.path,
    required this.type,
  });

  final String path;
  final CreateMediaType type;
}

class CameraCapturePage extends StatefulWidget {
  const CameraCapturePage({
    super.key,
    required this.initialMode,
  });

  final MediaPickerEntryMode initialMode;

  @override
  State<CameraCapturePage> createState() => _CameraCapturePageState();
}

class _CameraCapturePageState extends State<CameraCapturePage> {
  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  int _cameraIndex = 0;
  bool _isRecording = false;
  bool _isBusy = true;
  String? _error;
  late MediaPickerEntryMode _mode;

  @override
  void initState() {
    super.initState();
    _mode = widget.initialMode;
    _initCamera();
  }

  @override
  void dispose() {
    unawaited(_controller?.dispose());
    super.dispose();
  }

  Future<void> _initCamera() async {
    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) {
        setState(() {
          _error = UITextConstants.cameraUnavailable;
          _isBusy = false;
        });
        return;
      }
      await _initControllerByIndex(_cameraIndex);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = UITextConstants.cameraUnavailable;
        _isBusy = false;
      });
    }
  }

  Future<void> _initControllerByIndex(int index) async {
    final next = CameraController(
      _cameras[index],
      ResolutionPreset.high,
      enableAudio: true,
    );
    await _controller?.dispose();
    _controller = next;
    await _controller!.initialize();
    if (!mounted) return;
    setState(() {
      _cameraIndex = index;
      _error = null;
      _isBusy = false;
    });
  }

  Future<void> _toggleCamera() async {
    if (_cameras.length <= 1 || _isBusy) return;
    final next = (_cameraIndex + 1) % _cameras.length;
    setState(() => _isBusy = true);
    await _initControllerByIndex(next);
  }

  Future<void> _takePhoto() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized || _isBusy) return;
    setState(() => _isBusy = true);
    try {
      final file = await controller.takePicture();
      if (!mounted) return;
      Navigator.of(context).pop(
        CameraCaptureResult(path: file.path, type: CreateMediaType.image),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = UITextConstants.cameraCaptureFailed;
        _isBusy = false;
      });
    }
  }

  Future<void> _toggleRecord() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized || _isBusy) return;
    if (_isRecording) {
      setState(() => _isBusy = true);
      try {
        final file = await controller.stopVideoRecording();
        if (!mounted) return;
        Navigator.of(context).pop(
          CameraCaptureResult(path: file.path, type: CreateMediaType.video),
        );
      } catch (_) {
        if (!mounted) return;
        setState(() {
          _error = UITextConstants.cameraCaptureFailed;
          _isBusy = false;
          _isRecording = false;
        });
      }
      return;
    }
    setState(() => _isBusy = true);
    try {
      await controller.startVideoRecording();
      if (!mounted) return;
      setState(() {
        _isRecording = true;
        _isBusy = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = UITextConstants.cameraCaptureFailed;
        _isBusy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final subtle = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final controller = _controller;
    final canPreview = controller != null && controller.value.isInitialized;
    return Scaffold(
      backgroundColor: bg,
      body: SafeArea(
        child: Column(
          children: [
            SizedBox(
              height: AppSpacing.toolbarHeight,
              child: Row(
                children: [
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: Icon(Icons.close, color: fg),
                  ),
                  Expanded(
                    child: Center(
                      child: Text(
                        _mode == MediaPickerEntryMode.image
                            ? UITextConstants.cameraPhotoMode
                            : UITextConstants.cameraVideoMode,
                        style: TextStyle(
                          color: fg,
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: _toggleCamera,
                    icon: Icon(Icons.cameraswitch_outlined, color: fg),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Container(
                margin: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                  color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                ),
                clipBehavior: Clip.antiAlias,
                child: canPreview
                    ? CameraPreview(controller)
                    : Center(
                        child: _error == null
                            ? CupertinoActivityIndicator()
                            : Text(
                                _error!,
                                style: TextStyle(color: subtle, fontSize: AppTypography.base),
                              ),
                      ),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupSm),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _modeButton(
                  isDark: isDark,
                  active: _mode == MediaPickerEntryMode.image,
                  text: UITextConstants.cameraPhotoMode,
                  onTap: () => setState(() => _mode = MediaPickerEntryMode.image),
                ),
                SizedBox(width: AppSpacing.interGroupSm),
                _modeButton(
                  isDark: isDark,
                  active: _mode == MediaPickerEntryMode.video,
                  text: UITextConstants.cameraVideoMode,
                  onTap: () => setState(() => _mode = MediaPickerEntryMode.video),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.interGroupSm),
            SizedBox(
              height: AppSpacing.buttonHeight + AppSpacing.buttonHeightSm,
              child: Center(
                child: GestureDetector(
                  onTap: _mode == MediaPickerEntryMode.image ? _takePhoto : _toggleRecord,
                  child: Container(
                    width: AppSpacing.buttonHeight + AppSpacing.buttonHeightSm,
                    height: AppSpacing.buttonHeight + AppSpacing.buttonHeightSm,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(color: Colors.white, width: AppSpacing.intraGroupXs / 2),
                      color: _mode == MediaPickerEntryMode.video && _isRecording
                          ? AppColors.error
                          : AppColors.primaryColor,
                    ),
                    child: Icon(
                      _mode == MediaPickerEntryMode.image
                          ? Icons.camera_alt_outlined
                          : (_isRecording ? Icons.stop : Icons.videocam_outlined),
                      color: Colors.white,
                      size: AppSpacing.iconMedium,
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupLg),
          ],
        ),
      ),
    );
  }

  Widget _modeButton({
    required bool isDark,
    required bool active,
    required String text,
    required VoidCallback onTap,
  }) {
    final bg = active
        ? AppColors.primaryColor
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    final fg = active
        ? Colors.white
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          text,
          style: TextStyle(
            color: fg,
            fontSize: AppTypography.base,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}
