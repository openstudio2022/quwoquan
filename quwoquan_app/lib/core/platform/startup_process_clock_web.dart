import 'dart:js_interop';

@JS('__qwqStartupElapsedMs')
external JSNumber _webStartupElapsedMs();

@JS('__qwqRecordStartupEvent')
external void _webRecordStartupEvent(JSString json);

int? readPlatformStartupElapsedMs() {
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
