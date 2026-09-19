import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';

/// 当前账号的资料编辑快照与二维码读面。
abstract interface class ProfileEditQuery {
  Future<ProfileEditSnapshotData> getProfileEditSnapshot();

  Future<ProfileQrCardData> getProfileQrCard();
}
