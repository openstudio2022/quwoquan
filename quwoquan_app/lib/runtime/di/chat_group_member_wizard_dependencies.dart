import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/start_group_member_wizard.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/start_group_member_wizard_provider.dart';

final startGroupMemberWizardProvider =
    NotifierProvider.family<
      StartGroupMemberWizardController,
      StartGroupMemberWizardState,
      String
    >(StartGroupMemberWizardController.new);
