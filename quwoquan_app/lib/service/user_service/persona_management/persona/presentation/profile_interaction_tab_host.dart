import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_selection.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_participant_slots.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/share_interaction/share_interaction_list.dart';

/// Persona-owned host for the profile interaction participant surface.
///
/// The Content widget is supplied through [ProfileParticipantSlots], so this
/// object does not import another object's private presentation.
final class ProfileInteractionTabHost extends StatelessWidget {
  const ProfileInteractionTabHost({
    super.key,
    required this.participantSlots,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
    this.secondaryTabBarKey,
    this.onSecondaryHorizontalDragEnd,
    this.onDirectionSelected,
  });

  final ProfileParticipantSlots participantSlots;
  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;
  final ValueChanged<InteractionDirection>? onDirectionSelected;

  @override
  Widget build(BuildContext context) {
    return participantSlots.buildInteraction(
      mode: mode,
      userId: userId,
      isDark: isDark,
      inlineScroll: inlineScroll,
      secondaryTabBarKey: secondaryTabBarKey,
      onSecondaryHorizontalDragEnd: onSecondaryHorizontalDragEnd,
      onDirectionSelected: onDirectionSelected,
      shareInteractionBuilder:
          ({required direction, required personaId, required inlineScroll}) =>
              ShareInteractionList(
                direction: direction,
                personaId: personaId,
                inlineScroll: inlineScroll,
              ),
    );
  }
}
