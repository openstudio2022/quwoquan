import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/picker/desktop/desktop_picker_services.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('shouldUseDesktopImagePicker（能力位路由判据）', () {
    test('桌面（无系统相册 + 有本机文件系统）的图片入口走桌面选择器', () {
      expect(
        shouldUseDesktopImagePicker(
          CapabilityProfile.desktop,
          MediaPickerEntryMode.image,
        ),
        isTrue,
      );
    });

    test('移动端（有系统相册）图片入口不走桌面选择器', () {
      expect(
        shouldUseDesktopImagePicker(
          CapabilityProfile.mobile,
          MediaPickerEntryMode.image,
        ),
        isFalse,
      );
    });

    test('web（有系统相册但无本机文件系统）不走桌面选择器', () {
      expect(
        shouldUseDesktopImagePicker(
          CapabilityProfile.web,
          MediaPickerEntryMode.image,
        ),
        isFalse,
      );
    });

    test('桌面的视频入口不走桌面图片选择器', () {
      expect(
        shouldUseDesktopImagePicker(
          CapabilityProfile.desktop,
          MediaPickerEntryMode.video,
        ),
        isFalse,
      );
    });
  });

  group('PrefsDesktopPickerDirectoryMemory（记忆上次目录）', () {
    test('记忆 -> 读取回环；未记忆时为 null', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final memory = PrefsDesktopPickerDirectoryMemory(
        prefsFactory: SharedPreferences.getInstance,
      );

      expect(await memory.lastDirectory(), isNull);

      await memory.rememberDirectory('/Users/me/Pictures');
      expect(await memory.lastDirectory(), '/Users/me/Pictures');

      // 覆盖写入。
      await memory.rememberDirectory('/Users/me/Trips');
      expect(await memory.lastDirectory(), '/Users/me/Trips');
    });

    test('空路径不写入', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final memory = PrefsDesktopPickerDirectoryMemory(
        prefsFactory: SharedPreferences.getInstance,
      );
      await memory.rememberDirectory('');
      expect(await memory.lastDirectory(), isNull);
    });
  });
}
