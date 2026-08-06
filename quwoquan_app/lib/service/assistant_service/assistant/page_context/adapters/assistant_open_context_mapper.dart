import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

AssistantContextSnapshot assistantContextSnapshotFromOpenContext(
  AssistantOpenContext context, {
  String? userAction,
}) {
  final now = DateTime.now().toUtc();
  final pageType = assistantPageTypeForSource(context.source);
  final objectType = context.objectType?.trim() ?? '';
  final objectId = context.entityId?.trim() ?? '';
  final normalizedAction = userAction?.trim() ?? '';
  return AssistantContextSnapshot(
    capturedAt: now,
    pageType: pageType,
    pageObjects: <AssistantObjectGroundingView>[
      if (objectType.isNotEmpty && objectId.isNotEmpty)
        AssistantObjectGroundingView(
          objectTypeRef: objectType,
          objectId: objectId,
        ),
    ],
    userActions: <AssistantUserActionGroundingView>[
      if (normalizedAction.isNotEmpty)
        AssistantUserActionGroundingView(
          action: normalizedAction,
          objectTypeRef: objectType.isEmpty ? null : objectType,
          objectId: objectId.isEmpty ? null : objectId,
          occurredAt: now,
        ),
    ],
    consentMatrix: const AssistantConsentMatrix(canReadCurrentPage: true),
  );
}

/// 将端侧页面上下文映射到 PageContext 对象的 canonical generated wire。
PageContextSnapshot pageContextSnapshotFromOpenContext(
  AssistantOpenContext context, {
  String? userAction,
}) {
  final now = DateTime.now().toUtc();
  final objectType = context.objectType?.trim() ?? '';
  final objectId = context.entityId?.trim() ?? '';
  final normalizedAction = userAction?.trim() ?? '';
  return PageContextSnapshot(
    capturedAt: now,
    pageType: assistantPageTypeForSource(context.source),
    pageObjects: <PageContextObjectRef>[
      if (objectType.isNotEmpty && objectId.isNotEmpty)
        PageContextObjectRef(objectTypeRef: objectType, objectId: objectId),
    ],
    userActions: <PageContextAction>[
      if (normalizedAction.isNotEmpty)
        PageContextAction(
          actionType: normalizedAction,
          objectTypeRef: objectType.isEmpty ? null : objectType,
          objectId: objectId.isEmpty ? null : objectId,
        ),
    ],
    consentGranted: true,
  );
}
