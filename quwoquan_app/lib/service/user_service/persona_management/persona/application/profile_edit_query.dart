import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 当前账号的资料编辑快照与二维码读面。
abstract interface class ProfileEditQuery {
  Future<ProfileEditSnapshotData> getProfileEditSnapshot();

  Future<ProfileQrCardData> getProfileQrCard();

  Future<ProfileQrResolveWire> resolveProfileQrToken({
    required String token,
    String handle = '',
  });
}
