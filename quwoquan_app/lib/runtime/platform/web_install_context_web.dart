import 'dart:js_interop';

@JS('__qwqReadWebInstallContext')
external JSString _readWebInstallContext();

@JS('__qwqDismissWebInstall')
external void _dismissWebInstall();

String readWebInstallContextJson() => _readWebInstallContext().toDart;

void persistWebInstallDismissal() => _dismissWebInstall();
