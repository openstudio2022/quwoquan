import 'package:flutter_test/flutter_test.dart';

import 'remote_media_publication_uat_support.dart';

void main() {
  test(
    '真实 Remote：图片 complete 丢响应后恢复、处理完成并发布后可读',
    () => runRemoteMediaPublicationUat('photo'),
    skip: !kRunRemoteMediaPublicationUat,
    timeout: const Timeout(Duration(minutes: 5)),
  );
}
