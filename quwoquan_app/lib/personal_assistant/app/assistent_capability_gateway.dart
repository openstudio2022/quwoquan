import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';

typedef AssistentCapabilityRouteMode = CapabilityRouteMode;

class AssistentCapabilityGateway extends CapabilityGateway {
  AssistentCapabilityGateway({
    required super.assistantGateway,
    required super.openClawBridge,
  });
}

