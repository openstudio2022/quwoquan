import 'dart:async';

typedef OtpAutofillCodeListener = void Function(String code);

abstract interface class OtpAutofillGateway {
  Future<void> start(OtpAutofillCodeListener onCode);
  void bindRequestRef(String requestRef);
  Future<void> stop();
}

OtpAutofillGateway createOtpAutofillGateway() =>
    const SystemOtpAutofillGateway();

final class SystemOtpAutofillGateway implements OtpAutofillGateway {
  const SystemOtpAutofillGateway();

  @override
  void bindRequestRef(String requestRef) {}

  @override
  Future<void> start(OtpAutofillCodeListener onCode) async {}

  @override
  Future<void> stop() async {}
}
