import 'package:flutter/services.dart' show AssetBundle;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/assistant_run_policy_text_source.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';

final class FlutterAssistantRunPolicyTextSource
    implements AssistantRunPolicyTextSource {
  const FlutterAssistantRunPolicyTextSource({
    required this.assetBundle,
    required this.fileStorageGateway,
  });

  final AssetBundle assetBundle;
  final FileStorageGateway fileStorageGateway;

  @override
  Future<String> read(String path) async {
    try {
      return await assetBundle.loadString(path);
    } catch (error, stackTrace) {
      if (!fileStorageGateway.isSupported ||
          !await fileStorageGateway.exists(path)) {
        Error.throwWithStackTrace(error, stackTrace);
      }
      return fileStorageGateway.readAsString(path);
    }
  }
}
