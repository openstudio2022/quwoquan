import 'package:quwoquan_app/core/quwoquan_core.dart';

class ChatConversationAvatarTokens {
  const ChatConversationAvatarTokens._();

  static const double listSize = 52.0;
  static const double leadingGap = AppSpacing.sm + AppSpacing.xs;
  static const double placeholderIconScale = 0.54;

  static double dividerInset(double avatarSize) => avatarSize + leadingGap;
}
