import 'dart:js_interop';

@JS('__qwqStartupElapsedMs')
external JSNumber _webStartupElapsedMs();

@JS('__qwqRecordStartupEvent')
external void _webRecordStartupEvent(JSString json);

/// 返回 null 表示宿主页面没有安装启动探针，不表示测量失败；与 stub 实现同义。
int? tryReadPlatformStartupElapsedMs() {
  try {
    return _webStartupElapsedMs().toDartDouble.round();
  } catch (_) {
    return null;
  }
}

String readPlatformStartupDeadlineOrigin() => 'web_bootstrap';

void recordPlatformStartupEvent(String json) {
  try {
    _webRecordStartupEvent(json.toJS);
  } catch (_) {
    // 页面未安装 probe hook 时保持 best effort。
  }
}
