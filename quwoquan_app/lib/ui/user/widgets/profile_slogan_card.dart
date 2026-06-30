import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/components/object_page/object_slogan_card.dart';

/// 用户主页签名卡 —— 共享 [ObjectSloganCard] 的薄封装。
///
/// 真相源已下沉到 `object_page/object_slogan_card.dart`；此处仅保留用户主页既有的
/// 构造签名与 `profile-slogan-card` 根 key，保证像素与既有断言不变。
class ProfileSloganCard extends StatelessWidget {
  const ProfileSloganCard({
    super.key,
    required this.isDark,
    required this.bio,
    this.showEmptyPrompt = false,
    this.onTap,
  });

  final bool isDark;
  final String? bio;
  final bool showEmptyPrompt;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ObjectSloganCard(
      isDark: isDark,
      bio: bio,
      showEmptyPrompt: showEmptyPrompt,
      onTap: onTap,
      cardKey: const ValueKey<String>('profile-slogan-card'),
    );
  }
}
