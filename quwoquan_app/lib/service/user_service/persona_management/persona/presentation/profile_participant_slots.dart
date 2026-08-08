import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_selection.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';

typedef ProfileShareInteractionSlotBuilder =
    Widget Function({
      required ShareInteractionDirection direction,
      required String personaId,
      required bool inlineScroll,
    });

typedef ProfileInteractionSlotBuilder =
    Widget Function({
      required ProfileMode mode,
      required String userId,
      required bool isDark,
      required bool inlineScroll,
      required GlobalKey? secondaryTabBarKey,
      required GestureDragEndCallback? onSecondaryHorizontalDragEnd,
      required ValueChanged<InteractionDirection>? onDirectionSelected,
      required ProfileShareInteractionSlotBuilder shareInteractionBuilder,
    });

typedef ProfileFootprintSlotBuilder =
    Widget Function({
      required bool isDark,
      required GestureDragEndCallback? onSecondaryHorizontalDragEnd,
    });

typedef ProfileCirclesSlotBuilder =
    Widget Function({
      required ProfileMode mode,
      required String userId,
      required bool isDark,
      required bool inlineScroll,
    });

/// Persona 页面 source owner 对 Content/Circle 参与对象的 typed UI 插槽。
///
/// 具体参与对象 Widget 只在 runtime/di 绑定；ProfileShell 不导入兄弟对象的
/// private presentation，也不因物理归档改变页面 participant 身份。
final class ProfileParticipantSlots {
  const ProfileParticipantSlots({
    required this.buildInteraction,
    required this.buildFootprint,
    required this.buildCircles,
  });

  final ProfileInteractionSlotBuilder buildInteraction;
  final ProfileFootprintSlotBuilder buildFootprint;
  final ProfileCirclesSlotBuilder buildCircles;
}
