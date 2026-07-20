import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_resolve_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';

/// 当前账号的资料编辑快照与二维码读面。
abstract interface class ProfileEditQuery {
  Future<ProfileEditSnapshotData> getProfileEditSnapshot();

  Future<ProfileQrCardData> getProfileQrCard();

  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
    required String token,
    String handle = '',
  });
}
