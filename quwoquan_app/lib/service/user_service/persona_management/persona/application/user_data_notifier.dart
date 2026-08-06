import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_snapshot.dart';

/// 当前主体的公开资料快照 — 通过对象级 ProfileQuery 加载档案。
class UserDataNotifier extends Notifier<PersonaProfileSnapshot?> {
  @override
  PersonaProfileSnapshot? build() {
    return null;
  }

  Future<void> loadUser(
    String userId, {
    required AppUiSurface sourceSurface,
  }) async {
    try {
      final profile = await ref
          .read(profileQueryProvider(sourceSurface))
          .getUserProfile(userId);
      // 本地选取（相册/拍照）但尚未上传的临时文件路径原样保留（alpha 保存后即时回显），
      // 不经媒体解析器拼成不可访问 URL；服务端对象键 / 远端地址仍正常解析。
      final avatarUrl = isLocalFileImageSource(profile.avatarUrl)
          ? profile.avatarUrl
          : resolveAvatarImageUrl(
              profile.avatarUrl,
              avatarVersion: profile.avatarVersion,
            );
      final backgroundUrl = isLocalFileImageSource(profile.backgroundUrl)
          ? profile.backgroundUrl
          : resolveContentMediaUrl(profile.backgroundUrl);
      final personaId = profile.personaId.isNotEmpty
          ? profile.personaId
          : userId;
      state = PersonaProfileSnapshot(
        personaId: personaId,
        ownerUserId: profile.ownerUserId,
        userHandle: profile.userHandle,
        displayName: profile.displayName.isNotEmpty
            ? profile.displayName
            : null,
        avatarUrl: avatarUrl,
        bio: profile.bio.isNotEmpty ? profile.bio : null,
        backgroundImage: backgroundUrl.isNotEmpty ? backgroundUrl : null,
      );
    } catch (_) {
      // 这里是跨页面共享的已验证资料快照，不能把读取失败伪装成一个“真实”
      // 用户。仅可保留同一主体此前已成功加载的快照；主体切换或首读失败时清空，
      // 由 ProfileShell 的同源 ProfileQuery 失败态呈现恢复动作。
      if (state?.personaId != userId) {
        state = null;
      }
    }
  }
}

final userDataProvider =
    NotifierProvider<UserDataNotifier, PersonaProfileSnapshot?>(() {
      return UserDataNotifier();
    });
