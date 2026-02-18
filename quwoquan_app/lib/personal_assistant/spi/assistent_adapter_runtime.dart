import 'package:quwoquan_app/personal_assistant/spi/assistent_adapter_registry.dart';
import 'package:quwoquan_app/personal_assistant/spi/assistent_adapter_spi.dart';

class AssistentAdapterRuntime {
  AssistentAdapterRuntime(this._registry);

  final AssistentAdapterRegistry _registry;

  List<String> listAdapterIds() => _registry.listAdapterIds();

  Future<AssistentChannelEvent?> parseIncoming({
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

  Future<AssistentAdapterResponse?> dispatch({
    required String adapterId,
    required AssistentChannelEvent sourceEvent,
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

