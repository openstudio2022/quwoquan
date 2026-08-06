enum ProfileMediaTarget { avatar, cover }

class ProfileMediaUploadResult {
  const ProfileMediaUploadResult({required this.assetId});

  final String assetId;
}

abstract class ProfileMediaUploadGateway {
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  });
}
