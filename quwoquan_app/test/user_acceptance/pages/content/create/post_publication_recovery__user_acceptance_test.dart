import 'package:flutter_test/flutter_test.dart';

import 'remote_media_publication_uat_support.dart';

void main() {
  test(
    '真实 Remote：上传完成丢响应的权威状态恢复及临时对象取消',
    () => runRemoteMediaPublicationUat('recovery'),
    skip: !kRunRemoteMediaPublicationUat,
    timeout: const Timeout(Duration(minutes: 5)),
  );
}
