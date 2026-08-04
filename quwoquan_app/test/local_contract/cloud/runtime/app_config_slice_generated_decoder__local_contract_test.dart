import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('AppConfigSlice generated decoder 拒绝 camelCase 第二 wire 形态', () {
    expect(
      () => ContentAppConfig.fromWire(<String, Object?>{
        'featureFlags': const <String, Object?>{},
        'grayRelease': const <String, Object?>{},
      }),
      throwsFormatException,
    );
  });
}
