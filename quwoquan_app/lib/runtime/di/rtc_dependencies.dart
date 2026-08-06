import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_lifecycle_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_media_control_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_participant_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_query_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_screen_share_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// rtc domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum RtcProductionAdapter {
  callLifecycle,
  callMediaControl,
  callParticipant,
  callQuery,
  callScreenShare,
}

/// rtc domain 的唯一 production 装配入口。
final class RtcProductionComposition {
  const RtcProductionComposition._();

  static T generatedAdapter<T>(
    RtcProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      RtcProductionAdapter.callLifecycle => RemoteCallLifecycleCommandWriter(
        client: client,
        invocationContext: context,
      ),
      RtcProductionAdapter.callMediaControl => RemoteCallMediaControlWriter(
        client: client,
        invocationContext: context,
      ),
      RtcProductionAdapter.callParticipant =>
        RemoteCallParticipantCommandWriter(
          client: client,
          invocationContext: context,
        ),
      RtcProductionAdapter.callQuery => RemoteCallQuery(
        client: client,
        invocationContext: context,
      ),
      RtcProductionAdapter.callScreenShare => RemoteCallScreenShareWriter(
        client: client,
        invocationContext: context,
      ),
    };
    return result as T;
  }
}
