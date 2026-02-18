import 'package:quwoquan_app/personal_assistant/spi/assistent_adapter_spi.dart';

class AssistentAdapterRegistry {
  final Map<String, AssistentAdapterSpi> _adapters = <String, AssistentAdapterSpi>{};

  void register(AssistentAdapterSpi adapter) {
    _adapters[adapter.adapterId] = adapter;
  }

  AssistentAdapterSpi? byId(String adapterId) => _adapters[adapterId];

  List<String> listAdapterIds() => _adapters.keys.toList(growable: false);
}

