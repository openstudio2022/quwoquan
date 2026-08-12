/// 短期 OTP 发送意图。只保存恢复发送/倒计时所需字段，绝不保存验证码。
final class PendingOtpAttempt {
  const PendingOtpAttempt({
    required this.phone,
    required this.maskedPhone,
    required this.idempotencyKey,
    required this.deliveryStatus,
    required this.resendDeadlineEpochMs,
    required this.expiresAtEpochMs,
    this.challengeId = '',
    this.requestId = '',
  });

  final String phone;
  final String maskedPhone;
  final String idempotencyKey;
  final String challengeId;
  final String requestId;
  final String deliveryStatus;
  final int resendDeadlineEpochMs;
  final int expiresAtEpochMs;

  bool isExpired(DateTime now) =>
      expiresAtEpochMs <= now.millisecondsSinceEpoch;

  Map<String, Object?> toJson() => <String, Object?>{
    'phone': phone,
    'maskedPhone': maskedPhone,
    'idempotencyKey': idempotencyKey,
    'challengeId': challengeId,
    'requestId': requestId,
    'deliveryStatus': deliveryStatus,
    'resendDeadlineEpochMs': resendDeadlineEpochMs,
    'expiresAtEpochMs': expiresAtEpochMs,
  };

  static PendingOtpAttempt? tryParse(Object? value) {
    if (value is! Map) return null;
    final map = value.cast<Object?, Object?>();
    final phone = map['phone'];
    final maskedPhone = map['maskedPhone'];
    final idempotencyKey = map['idempotencyKey'];
    final challengeId = map['challengeId'];
    final requestId = map['requestId'];
    final deliveryStatus = map['deliveryStatus'];
    final resendDeadlineEpochMs = map['resendDeadlineEpochMs'];
    final expiresAtEpochMs = map['expiresAtEpochMs'];
    if (phone is! String ||
        maskedPhone is! String ||
        idempotencyKey is! String ||
        challengeId is! String ||
        requestId is! String ||
        deliveryStatus is! String ||
        resendDeadlineEpochMs is! int ||
        expiresAtEpochMs is! int ||
        idempotencyKey.trim().length < 16) {
      return null;
    }
    return PendingOtpAttempt(
      phone: phone,
      maskedPhone: maskedPhone,
      idempotencyKey: idempotencyKey,
      challengeId: challengeId,
      requestId: requestId,
      deliveryStatus: deliveryStatus,
      resendDeadlineEpochMs: resendDeadlineEpochMs,
      expiresAtEpochMs: expiresAtEpochMs,
    );
  }
}

abstract interface class PendingOtpAttemptStore {
  Future<PendingOtpAttempt?> read();

  Future<void> write(PendingOtpAttempt attempt);

  Future<void> clear();
}
