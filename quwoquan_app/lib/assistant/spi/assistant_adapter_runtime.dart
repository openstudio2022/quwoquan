import 'dart:convert';

import 'package:quwoquan_app/assistant/security/assistant_security_runtime.dart';

class AssistantChannelEvent {
  const AssistantChannelEvent({
    required this.channel,
    required this.eventType,
    required this.payload,
  });

  final String channel;
  final String eventType;
  final Map<String, dynamic> payload;
}

class AssistantAdapterResponse {
  const AssistantAdapterResponse({
    required this.ok,
    required this.message,
    this.payload = const <String, dynamic>{},
  });

  final bool ok;
  final String message;
  final Map<String, dynamic> payload;
}

abstract class AssistantAdapterSpi {
  String get adapterId;

  Future<bool> verify(Map<String, String> headers, String rawBody);

  Future<AssistantChannelEvent> ingest({
    required Map<String, String> headers,
    required String rawBody,
  });

  Future<AssistantAdapterResponse> dispatch({
    required AssistantChannelEvent sourceEvent,
    required Map<String, dynamic> responseEnvelope,
  });
}

class AssistantAdapterRegistry {
  final Map<String, AssistantAdapterSpi> _adapters =
      <String, AssistantAdapterSpi>{};

  void register(AssistantAdapterSpi adapter) {
    _adapters[adapter.adapterId] = adapter;
  }

  AssistantAdapterSpi? byId(String adapterId) => _adapters[adapterId];

  List<String> listAdapterIds() => _adapters.keys.toList(growable: false);
}

class AssistantAdapterRuntime {
  AssistantAdapterRuntime(this._registry);

  final AssistantAdapterRegistry _registry;

  List<String> listAdapterIds() => _registry.listAdapterIds();

  Future<AssistantChannelEvent?> parseIncoming({
    required String adapterId,
    required Map<String, String> headers,
    required String rawBody,
  }) async {
    final adapter = _registry.byId(adapterId);
    if (adapter == null) return null;
    final verified = await adapter.verify(headers, rawBody);
    if (!verified) return null;
    return adapter.ingest(headers: headers, rawBody: rawBody);
  }

  Future<AssistantAdapterResponse?> dispatch({
    required String adapterId,
    required AssistantChannelEvent sourceEvent,
    required Map<String, dynamic> responseEnvelope,
  }) async {
    final adapter = _registry.byId(adapterId);
    if (adapter == null) return null;
    return adapter.dispatch(
      sourceEvent: sourceEvent,
      responseEnvelope: responseEnvelope,
    );
  }
}

class AssistantFeishuAdapter implements AssistantAdapterSpi {
  AssistantFeishuAdapter({
    required AssistantSignaturePolicy signaturePolicy,
    AssistantSignatureValidator? signatureValidator,
  }) : _signaturePolicy = signaturePolicy,
       _signatureValidator =
           signatureValidator ?? const AssistantSignatureValidator();

  final AssistantSignaturePolicy _signaturePolicy;
  final AssistantSignatureValidator _signatureValidator;

  @override
  String get adapterId => 'feishu';

  @override
  Future<AssistantAdapterResponse> dispatch({
    required AssistantChannelEvent sourceEvent,
    required Map<String, dynamic> responseEnvelope,
  }) async {
    return AssistantAdapterResponse(
      ok: true,
      message: 'feishu dispatch simulated',
      payload: <String, dynamic>{
        'channel': sourceEvent.channel,
        'responseEnvelope': responseEnvelope,
      },
    );
  }

  @override
  Future<AssistantChannelEvent> ingest({
    required Map<String, String> headers,
    required String rawBody,
  }) async {
    final decoded = jsonDecode(rawBody);
    final map = decoded is Map
        ? decoded.cast<String, dynamic>()
        : <String, dynamic>{};
    final text = map['text']?.toString() ?? map['content']?.toString() ?? '';
    return AssistantChannelEvent(
      channel: 'feishu',
      eventType: 'message',
      payload: <String, dynamic>{'text': text, 'raw': map},
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

class AssistantOpenclawAdapter implements AssistantAdapterSpi {
  AssistantOpenclawAdapter({
    required AssistantSignaturePolicy signaturePolicy,
    AssistantSignatureValidator? signatureValidator,
  }) : _signaturePolicy = signaturePolicy,
       _signatureValidator =
           signatureValidator ?? const AssistantSignatureValidator();

  final AssistantSignaturePolicy _signaturePolicy;
  final AssistantSignatureValidator _signatureValidator;

  @override
  String get adapterId => 'openclaw';

  @override
  Future<AssistantAdapterResponse> dispatch({
    required AssistantChannelEvent sourceEvent,
    required Map<String, dynamic> responseEnvelope,
  }) async {
    return AssistantAdapterResponse(
      ok: true,
      message: 'openclaw dispatch simulated',
      payload: <String, dynamic>{
        'channel': sourceEvent.channel,
        'responseEnvelope': responseEnvelope,
      },
    );
  }

  @override
  Future<AssistantChannelEvent> ingest({
    required Map<String, String> headers,
    required String rawBody,
  }) async {
    final decoded = jsonDecode(rawBody);
    final map = decoded is Map
        ? decoded.cast<String, dynamic>()
        : <String, dynamic>{};
    final prompt = map['prompt']?.toString() ?? map['text']?.toString() ?? '';
    return AssistantChannelEvent(
      channel: 'openclaw',
      eventType: 'skill_invoke',
      payload: <String, dynamic>{'text': prompt, 'raw': map},
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
