import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_selection.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/presentation/profile_interaction_tab.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_state_provider.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/share_interaction/share_interaction_list.dart';

/// Composition root for the Persona profile shell and Content interaction view.
///
/// The Content object receives selection values and callbacks through its
/// public application contract; Persona-owned state and share presentation
/// remain private to Persona and are wired only here.
class ProfileInteractionTabComposition extends ConsumerWidget {
  const ProfileInteractionTabComposition({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
    this.secondaryTabBarKey,
    this.onSecondaryHorizontalDragEnd,
    this.onDirectionSelected,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;
  final ValueChanged<InteractionDirection>? onDirectionSelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(profileNotifierProvider(userId));
    final notifier = ref.read(profileNotifierProvider(userId).notifier);
    return ProfileInteractionTab(
      mode: mode,
      userId: userId,
      isDark: isDark,
      inlineScroll: inlineScroll,
      secondaryTabBarKey: secondaryTabBarKey,
      onSecondaryHorizontalDragEnd: onSecondaryHorizontalDragEnd,
      selectedSubTab: state.interactionSubTab,
      selectedDirection: state.interactionDirection,
      onSubTabSelected: notifier.setInteractionSubTab,
      onDirectionSelected:
          onDirectionSelected ?? notifier.setInteractionDirection,
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
