import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

class AssistantEdgeService {
  AssistantEdgeService._(this.runtime);

  final AssistantRuntime runtime;

  static AssistantEdgeService createDefault() {
    return AssistantEdgeService._(AssistantRuntime.createDefault());
  }

  static AssistantEdgeService createForTest({String? storagePath}) {
    return AssistantEdgeService._(
      AssistantRuntime.createForTest(storagePath: storagePath),
    );
  }

  Future<void> ensureRemoteConfigLoaded() {
    return runtime.ensureRemoteConfigLoaded();
  }

  bool switchModel(String modelRef) => runtime.switchModel(modelRef);

  List<String> listAvailableModels() => runtime.listAvailableModels();

  List<String> selectedModels() => runtime.selectedModels();

  bool setSelectedModels(List<String> modelRefs) {
    return runtime.setSelectedModels(modelRefs);
  }

  String? currentModel() => runtime.currentModel();
}
