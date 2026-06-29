import 'dart:io';

HttpOverrides? _previousOverrides;
bool _installed = false;

void installLocalApiContractBadCertificateOverride({required bool enabled}) {
  if (!enabled || _installed) return;
  _previousOverrides = HttpOverrides.current;
  HttpOverrides.global = _LocalApiContractHttpOverrides(_previousOverrides);
  _installed = true;
}

void restoreLocalApiContractBadCertificateOverride() {
  if (!_installed) return;
  HttpOverrides.global = _previousOverrides;
  _previousOverrides = null;
  _installed = false;
}

class _LocalApiContractHttpOverrides extends HttpOverrides {
  _LocalApiContractHttpOverrides(this._delegate);

  final HttpOverrides? _delegate;

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client =
        _delegate?.createHttpClient(context) ?? super.createHttpClient(context);
    client.badCertificateCallback = (certificate, host, port) {
      if (_isLocalApiContractHost(host)) return true;
      return false;
    };
    return client;
  }
}

bool _isLocalApiContractHost(String host) =>
    host == 'localhost' ||
    host.endsWith('.localhost') ||
    host.endsWith('.quwoquan-env.test');
