import 'dart:convert';

import 'package:quwoquan_app/personal_assistant/security/assistent_signature_validator.dart';
import 'package:quwoquan_app/personal_assistant/spi/assistent_adapter_spi.dart';

class AssistentOpenclawAdapter implements AssistentAdapterSpi {
  AssistentOpenclawAdapter({
    required AssistentSignaturePolicy signaturePolicy,
    AssistentSignatureValidator? signatureValidator,
  })  : _signaturePolicy = signaturePolicy,
        _signatureValidator = signatureValidator ?? const AssistentSignatureValidator();

  final AssistentSignaturePolicy _signaturePolicy;
  final AssistentSignatureValidator _signatureValidator;

  @override
  String get adapterId => 'openclaw';

  @override
  Future<AssistentAdapterResponse> dispatch({
    required AssistentChannelEvent sourceEvent,
    required Map<String, dynamic> responseEnvelope,
  }) async {
    return AssistentAdapterResponse(
      ok: true,
      message: 'openclaw dispatch simulated',
      payload: <String, dynamic>{
        'channel': sourceEvent.channel,
        'responseEnvelope': responseEnvelope,
      },
    );
  }

  @override
  Future<AssistentChannelEvent> ingest({
    required Map<String, String> headers,
    required String rawBody,
  }) async {
    final decoded = jsonDecode(rawBody);
    final map = decoded is Map ? decoded.cast<String, dynamic>() : <String, dynamic>{};
    final prompt = map['prompt']?.toString() ?? map['text']?.toString() ?? '';
    return AssistentChannelEvent(
      channel: 'openclaw',
      eventType: 'skill_invoke',
      payload: <String, dynamic>{
        'text': prompt,
        'raw': map,
      },
    );
  }

  @override
  Future<bool> verify(Map<String, String> headers, String rawBody) async {
    return _signatureValidator.validate(
      policy: _signaturePolicy,
      headers: headers,
      rawBody: rawBody,
    );
  }
}

