import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 由 composition root 注入的只读 operation 调用上下文工厂。
typedef CloudSurfaceQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId,
    );

/// 由 composition root 注入的写 operation 调用上下文工厂。
typedef CloudSurfaceCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    });
