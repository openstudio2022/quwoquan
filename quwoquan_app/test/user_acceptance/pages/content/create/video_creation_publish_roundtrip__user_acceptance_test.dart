import 'package:flutter_test/flutter_test.dart';

import 'remote_media_publication_uat_support.dart';

void main() {
  test(
    '真实 Remote：视频处理、自动封面、幂等发布与 readback',
    () => runRemoteMediaPublicationUat('video'),
    skip: !kRunRemoteMediaPublicationUat,
    timeout: const Timeout(Duration(minutes: 5)),
  );
}
