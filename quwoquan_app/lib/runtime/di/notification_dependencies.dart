import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/adapters/app_message_facets_remote.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/adapters/incoming_call_presentation_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// notification domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum NotificationProductionAdapter { incomingCallPresentation }

final class AppProductionAppMessageFacets {
  const AppProductionAppMessageFacets({
    required this.query,
    required this.commandWriter,
  });

  final AppMessageQuery query;
  final AppMessageCommandWriter commandWriter;
}

/// notification domain 的唯一 production 装配入口。
final class NotificationProductionComposition {
  const NotificationProductionComposition._();

  static AppProductionAppMessageFacets appMessageFacets({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final remote = RemoteAppMessageAdapter(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
    return AppProductionAppMessageFacets(query: remote, commandWriter: remote);
  }

  static T generatedAdapter<T>(
    NotificationProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      NotificationProductionAdapter.incomingCallPresentation =>
        RemoteIncomingCallPresentationAcknowledger(
          client: client,
          invocationContext: context,
        ),
    };
    return result as T;
  }
}
