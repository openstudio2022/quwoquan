import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/runtime/shell/startup/startup_content_warmup_port.dart';

/// 启动内容预热的唯一 production 组装点。
final startupContentWarmupPortProvider = Provider<StartupContentWarmupPort>(
  _PostPublicationStartupWarmupPort.new,
);

final class _PostPublicationStartupWarmupPort
    implements StartupContentWarmupPort {
  const _PostPublicationStartupWarmupPort(this._ref);

  final Ref _ref;

  @override
  void warmUp() {
    if (CloudRuntimeConfig.contentSource == AppContentSource.bundledSnapshot) {
      return;
    }
    _ref.read(postPublicationIntentQueueProvider);
  }
}
