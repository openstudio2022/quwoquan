import 'package:camera/camera.dart';

enum CameraPhotoSurfaceState {
  idle,
  ready,
  filterOpen,
  flashOpen,
  capturing,
  preview,
  recording,
  videoPreview,
  permissionDenied,
  error,
}

enum CameraPhotoCaller { picker, create }

enum CameraPhotoEntrySource { photoPicker, publishEntry }

enum CameraPhotoFlashMode { auto, off, on }

extension CameraPhotoFlashModeX on CameraPhotoFlashMode {
  FlashMode toCameraFlashMode() {
    switch (this) {
      case CameraPhotoFlashMode.auto:
        return FlashMode.auto;
      case CameraPhotoFlashMode.off:
        return FlashMode.off;
      case CameraPhotoFlashMode.on:
        return FlashMode.always;
    }
  }

  /// 视频摄像模式下右上角是连续“灯光/补光灯”，映射到摄像头持续补光（torch），
  /// 而不是拍照的闪光（always）。只有 off/on 两态参与视频。
  FlashMode toCameraTorchMode() {
    switch (this) {
      case CameraPhotoFlashMode.on:
        return FlashMode.torch;
      case CameraPhotoFlashMode.auto:
      case CameraPhotoFlashMode.off:
        return FlashMode.off;
    }
  }

  String get telemetryValue {
    switch (this) {
      case CameraPhotoFlashMode.auto:
        return 'auto';
      case CameraPhotoFlashMode.off:
        return 'off';
      case CameraPhotoFlashMode.on:
        return 'on';
    }
  }
}

extension CameraPhotoEntrySourceX on CameraPhotoEntrySource {
  String get telemetryValue {
    switch (this) {
      case CameraPhotoEntrySource.photoPicker:
        return 'photo_picker';
      case CameraPhotoEntrySource.publishEntry:
        return 'publish_entry';
    }
  }
}

extension CameraPhotoCallerX on CameraPhotoCaller {
  String get telemetryValue {
    switch (this) {
      case CameraPhotoCaller.picker:
        return 'picker';
      case CameraPhotoCaller.create:
        return 'create';
    }
  }
}
