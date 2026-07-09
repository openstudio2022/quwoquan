part of 'edit_profile_page.dart';

class _EditProfilePageState extends ConsumerState<EditProfilePage> {
  static const int _signatureMaxLength = 60;

  late final TextEditingController _nicknameController;
  ProfileEditSnapshotData? _initial;
  ProfileCredentialSummaryData? _phoneCredential;
  String _gender = 'unspecified';
  String _birthDate = '';
  String _region = '';
  String _regionTagRef = '';
  String _signature = '';
  String _occupationTagRef = '';
  List<String> _interestTagRefs = const <String>[];
  String? _pickedAvatarSource;
  String? _pickedCoverSource;
  bool _loading = true;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    final userData = ref.read(userDataProvider);
    _nicknameController = TextEditingController(
      text: (userData?.displayName ?? '').trim(),
    )..addListener(_handleFieldChanged);
    _signature = _limitSignature(userData?.bio ?? '');
    unawaited(_loadSnapshot());
  }

  @override
  void dispose() {
    _nicknameController.removeListener(_handleFieldChanged);
    _nicknameController.dispose();
    super.dispose();
  }

  Future<void> _loadSnapshot() async {
    try {
      final snapshot = await ref
          .read(userProfileRepositoryProvider)
          .getProfileEditSnapshot();
      if (!mounted) {
        return;
      }
      setState(() {
        _initial = snapshot;
        _phoneCredential = snapshot.phoneCredential;
        _nicknameController.text = snapshot.nickname;
        _gender = _normalizeGender(snapshot.gender);
        _birthDate = snapshot.birthDate;
        _region = snapshot.region;
        _regionTagRef = snapshot.regionTagRef;
        _signature = _limitSignature(snapshot.bio);
        _occupationTagRef = snapshot.occupationTagRef;
        _interestTagRefs = snapshot.interestTagRefs;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() => _loading = false);
    }
  }

  static String _limitSignature(String value) {
    return value.length <= _signatureMaxLength
        ? value
        : value.substring(0, _signatureMaxLength);
  }

  void _handleFieldChanged() {
    if (mounted) {
      setState(() {});
    }
  }

  String get _initialAvatar => _initial?.avatarUrl ?? '';
  String get _initialCover => _initial?.backgroundUrl ?? '';
  String get _initialHandle => _initial?.userHandle ?? '';
  String get _effectiveAvatar => _pickedAvatarSource ?? _initialAvatar;
  String get _effectiveCover => _pickedCoverSource ?? _initialCover;

  bool get _isDirty {
    final snapshot = _initial;
    if (snapshot == null) {
      return false;
    }
    return _nicknameController.text.trim() != snapshot.nickname ||
        _gender != _normalizeGender(snapshot.gender) ||
        _birthDate != snapshot.birthDate ||
        _region != snapshot.region ||
        _regionTagRef != snapshot.regionTagRef ||
        _signature != snapshot.bio ||
        _occupationTagRef != snapshot.occupationTagRef ||
        !_sameStringList(_interestTagRefs, snapshot.interestTagRefs) ||
        _pickedAvatarSource != null ||
        _pickedCoverSource != null;
  }

  Future<void> _handleBackRequest() async {
    if (!_isDirty) {
      _doClose();
      return;
    }
    final discard = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(UITextConstants.editProfileDiscardTitle),
          content: const Text(UITextConstants.editProfileDiscardMessage),
          actions: <Widget>[
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text(UITextConstants.editProfileDiscardConfirm),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text(UITextConstants.editProfileKeepEditing),
            ),
          ],
        );
      },
    );
    if (discard == true) {
      _doClose();
    }
  }

  void _doClose() {
    final navigator = Navigator.maybeOf(context);
    if (navigator != null && navigator.canPop()) {
      navigator.pop();
    }
  }

  Future<void> _save() async {
    final snapshot = _initial;
    if (snapshot == null || !_isDirty || _isSaving) {
      return;
    }
    setState(() => _isSaving = true);
    try {
      final mediaGateway = ref.read(profileMediaUploadGatewayProvider);
      final avatarUpload = _pickedAvatarSource == null
          ? null
          : await mediaGateway.uploadImage(
              localPath: _pickedAvatarSource!,
              target: ProfileMediaTarget.avatar,
            );
      final coverUpload = _pickedCoverSource == null
          ? null
          : await mediaGateway.uploadImage(
              localPath: _pickedCoverSource!,
              target: ProfileMediaTarget.cover,
            );
      await ref
          .read(userProfileRepositoryProvider)
          .updateProfile(
            ProfileEditUpdatePayload(
              nickname: _nicknameController.text.trim() != snapshot.nickname
                  ? _nicknameController.text.trim()
                  : null,
              bio: _signature != snapshot.bio ? _signature : null,
              avatarAssetId: avatarUpload?.assetId,
              avatarUrl: avatarUpload?.cdnUrl.isEmpty == true
                  ? null
                  : avatarUpload?.cdnUrl,
              backgroundAssetId: coverUpload?.assetId,
              backgroundUrl: coverUpload?.cdnUrl.isEmpty == true
                  ? null
                  : coverUpload?.cdnUrl,
              gender: _gender != _normalizeGender(snapshot.gender)
                  ? _gender
                  : null,
              birthDate: _birthDate != snapshot.birthDate ? _birthDate : null,
              regionTagRef: _regionTagRef != snapshot.regionTagRef
                  ? _regionTagRef
                  : null,
              occupationTagRef: _occupationTagRef != snapshot.occupationTagRef
                  ? _occupationTagRef
                  : null,
              interestTagRefs:
                  !_sameStringList(_interestTagRefs, snapshot.interestTagRefs)
                  ? _interestTagRefs
                  : null,
            ),
          );
      final currentUserId = ref.read(currentUserIdProvider);
      await ref.read(userDataProvider.notifier).loadUser(currentUserId);
      final _ = await ref.refresh(activePersonaContextProvider.future);
      if (currentUserId.isNotEmpty) {
        await ref
            .read(profileNotifierProvider(currentUserId).notifier)
            .loadProfile();
      }
      if (!mounted) {
        return;
      }
      setState(() => _isSaving = false);
      AppToast.show(context, UITextConstants.editProfileSavedToast);
      _doClose();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _isSaving = false);
      await _showSubmitError(error);
    }
  }

  Future<void> _showSubmitError(Object error) async {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: UITextConstants.editProfileSaveFailedTitle,
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.retry,
          label: UITextConstants.tryAgain,
        ),
        secondaryAction: resolved.secondaryAction,
        dismissible: resolved.dismissible,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        recoveryAction: resolved.recoveryAction,
        presentation: resolved.presentation,
        tone: resolved.tone,
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _save();
        }
      },
    );
  }

  Future<void> _pickMedia(_EditProfileMediaTarget target) async {
    final source = await showAppActionSheet<ImagePickSource>(
      context,
      title: target == _EditProfileMediaTarget.avatar
          ? UITextConstants.profileChangeAvatar
          : UITextConstants.profileChangeCover,
      sections: const <AppActionSheetSection<ImagePickSource>>[
        AppActionSheetSection<ImagePickSource>(
          items: <AppActionSheetItem<ImagePickSource>>[
            AppActionSheetItem<ImagePickSource>(
              value: ImagePickSource.camera,
              label: UITextConstants.editProfileMediaCamera,
              icon: CupertinoIcons.camera,
            ),
            AppActionSheetItem<ImagePickSource>(
              value: ImagePickSource.photoLibrary,
              label: UITextConstants.editProfileMediaPhotoLibrary,
              icon: CupertinoIcons.photo_on_rectangle,
            ),
          ],
        ),
      ],
    );
    if (!mounted || source == null) {
      return;
    }
    final path = await ref
        .read(imagePickGatewayProvider)
        .pickImage(
          context,
          source: source,
          cameraRouteName: PageAccessInternalRoutes.profileMediaPickerCamera,
          galleryRouteName: PageAccessInternalRoutes.profileMediaPickerGallery,
        );
    if (!mounted || path == null || path.trim().isEmpty) {
      return;
    }
    setState(() {
      switch (target) {
        case _EditProfileMediaTarget.avatar:
          _pickedAvatarSource = path.trim();
        case _EditProfileMediaTarget.cover:
          _pickedCoverSource = path.trim();
      }
    });
  }

  Future<void> _editNickname() async {
    final value = await Navigator.of(context).push<String>(
      CupertinoPageRoute<String>(
        builder: (_) => _TextEditPage(
          title: UITextConstants.editProfileNicknameLabel,
          initialValue: _nicknameController.text,
          placeholder: UITextConstants.editProfileNicknamePlaceholder,
          maxLength: 24,
          maxLines: 1,
        ),
      ),
    );
    if (value != null && mounted) {
      _nicknameController.text = value.trim();
    }
  }

  Future<void> _editGender() async {
    final next = await showAppActionSheet<String>(
      context,
      title: UITextConstants.editProfileGenderLabel,
      sections: const <AppActionSheetSection<String>>[
        AppActionSheetSection<String>(
          items: <AppActionSheetItem<String>>[
            AppActionSheetItem<String>(
              value: 'male',
              label: UITextConstants.editProfileGenderMale,
              icon: CupertinoIcons.person,
            ),
            AppActionSheetItem<String>(
              value: 'female',
              label: UITextConstants.editProfileGenderFemale,
              icon: CupertinoIcons.person,
            ),
            AppActionSheetItem<String>(
              value: 'unspecified',
              label: UITextConstants.editProfileGenderUnspecified,
              icon: CupertinoIcons.eye_slash,
            ),
          ],
        ),
      ],
    );
    if (next != null && mounted) {
      setState(() => _gender = next);
    }
  }

  Future<void> _editBirthday() async {
    final next = await Navigator.of(context).push<String>(
      CupertinoPageRoute<String>(
        builder: (_) => _BirthdayEditPage(initialValue: _birthDate),
      ),
    );
    if (next != null && mounted) {
      setState(() => _birthDate = next);
    }
  }

  Future<void> _editRegion() async {
    final result = await Navigator.of(context).push<_RegionPickResult>(
      CupertinoPageRoute<_RegionPickResult>(
        builder: (_) => _RegionPickerPage(selectedTagRef: _regionTagRef),
      ),
    );
    if (result != null && mounted) {
      setState(() {
        _region = result.display;
        _regionTagRef = result.tagRef;
      });
    }
  }

  Future<void> _editPhone() async {
    final result = await Navigator.of(context)
        .push<ProfileCredentialSummaryData>(
          CupertinoPageRoute<ProfileCredentialSummaryData>(
            builder: (_) => _PhoneBindPage(initialCredential: _phoneCredential),
          ),
        );
    if (result != null && mounted) {
      setState(() => _phoneCredential = result);
    }
  }

  Future<void> _showQrCode() async {
    await Navigator.of(context).push<void>(
      CupertinoPageRoute<void>(builder: (_) => const _ProfileQrCardPage()),
    );
  }

  Future<void> _editSignature() async {
    final value = await Navigator.of(context).push<String>(
      CupertinoPageRoute<String>(
        builder: (_) => _TextEditPage(
          title: UITextConstants.editProfileSignatureTitle,
          initialValue: _signature,
          placeholder: UITextConstants.editProfileSignaturePlaceholder,
          maxLength: _signatureMaxLength,
          maxLines: 4,
        ),
      ),
    );
    if (value != null && mounted) {
      setState(() => _signature = _limitSignature(value));
    }
  }

  Future<void> _editTags() async {
    final changed = await context.push<bool>(
      AppRoutePaths.profileCareerInterests,
    );
    if (changed == true && mounted) {
      setState(() => _loading = true);
      await _loadSnapshot();
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final canSave = _isDirty && !_isSaving;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          unawaited(_handleBackRequest());
        }
      },
      child: AppScaffold(
        backgroundColor: AppColors.iosPageBackground(context),
        navigationBar: AppNavigationBar(
          backgroundColor: AppColors.iosSystemBackground(context),
          border: Border(
            bottom: BorderSide(
              color: AppColors.iosSeparator(context).withValues(alpha: 0.36),
              width: AppSpacing.hairline,
            ),
          ),
          leading: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () => unawaited(_handleBackRequest()),
          ),
          middle: Text(
            UITextConstants.editProfile,
            style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
          ),
          trailing: CupertinoButton(
            key: const ValueKey<String>('edit-profile-save'),
            padding: EdgeInsets.zero,
            minimumSize: const Size.square(AppSpacing.minInteractiveSize),
            onPressed: canSave ? _save : null,
            child: Text(
              UITextConstants.editProfileSaveAction,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                fontWeight: AppTypography.medium,
                color: canSave
                    ? AppColors.iosAccent(context)
                    : AppColors.iosTertiaryLabel(context),
              ),
            ),
          ),
        ),
        body: _loading
            ? const Center(child: CupertinoActivityIndicator())
            : ListView(
                padding: EdgeInsets.fromLTRB(
                  0,
                  AppSpacing.containerSm,
                  0,
                  MediaQuery.viewPaddingOf(context).bottom +
                      AppSpacing.interGroupLg,
                ),
                children: <Widget>[
                  ProfileIosGroupedSection(
                    showDividers: true,
                    children: <Widget>[_buildCoverRow(), _buildAvatarRow()],
                  ),
                  ProfileIosGroupedSection(
                    showDividers: true,
                    children: <Widget>[
                      ProfileIosGroupedCell(
                        key: const ValueKey<String>(
                          'edit-profile-nickname-row',
                        ),
                        title: UITextConstants.editProfileNicknameLabel,
                        trailing: _EditProfileTrailingValue(
                          value: _valueOrPrompt(
                            _nicknameController.text.trim(),
                            prompt: UITextConstants.editProfileFillCtaValue,
                          ),
                        ),
                        onTap: _editNickname,
                      ),
                      ProfileIosGroupedCell(
                        title: UITextConstants.editProfileGenderLabel,
                        trailing: _EditProfileTrailingValue(
                          value: _EditProfileDisplayValue(
                            _genderLabel(_gender),
                          ),
                        ),
                        onTap: _editGender,
                      ),
                      ProfileIosGroupedCell(
                        title: UITextConstants.editProfileBirthdayLabel,
                        trailing: _EditProfileTrailingValue(
                          value: _valueOrPrompt(
                            _birthDate,
                            prompt: UITextConstants.editProfileFillCtaValue,
                          ),
                        ),
                        onTap: _editBirthday,
                      ),
                      ProfileIosGroupedCell(
                        title: UITextConstants.editProfileRegionLabel,
                        trailing: _EditProfileTrailingValue(
                          value: _regionDisplay(_region),
                        ),
                        onTap: _editRegion,
                      ),
                    ],
                  ),
                  ProfileIosGroupedSection(
                    showDividers: true,
                    children: <Widget>[
                      ProfileIosGroupedCell(
                        title: UITextConstants.editProfilePhoneLabel,
                        trailing: _EditProfileTrailingValue(
                          value: _phoneDisplay(_phoneCredential),
                        ),
                        onTap: _editPhone,
                      ),
                      ProfileIosGroupedCell(
                        title: UITextConstants.editProfileQuwoquanIdLabel,
                        showChevron: false,
                        trailing: _EditProfileTrailingValue(
                          value: _valueOrSystemFallback(
                            _initialHandle,
                            fallback: UITextConstants
                                .editProfileSystemGeneratingValue,
                          ),
                        ),
                      ),
                      ProfileIosGroupedCell(
                        title: UITextConstants.editProfileQrCodeLabel,
                        trailing: Icon(
                          CupertinoIcons.qrcode,
                          size: AppSpacing.iconMedium,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                        onTap: _showQrCode,
                      ),
                    ],
                  ),
                  ProfileIosGroupedSection(
                    showDividers: true,
                    children: <Widget>[
                      ProfileIosGroupedCell(
                        key: const ValueKey<String>(
                          'edit-profile-signature-row',
                        ),
                        title: UITextConstants.editProfileBioLabel,
                        trailing: _EditProfileTrailingValue(
                          value: _valueOrPrompt(
                            _signature,
                            prompt: UITextConstants.editProfileFillCtaValue,
                          ),
                        ),
                        onTap: _editSignature,
                      ),
                      ProfileIosGroupedCell(
                        title: UITextConstants.editProfileTagsLabel,
                        trailing: _EditProfileTrailingValue(
                          value: _tagsSummary(
                            _occupationTagRef,
                            _interestTagRefs,
                          ),
                        ),
                        onTap: _editTags,
                      ),
                    ],
                  ),
                ],
              ),
      ),
    );
  }

  Widget _buildCoverRow() {
    return ProfileIosGroupedCell(
      title: UITextConstants.editProfileCoverLabel,
      minHeight: _EditProfileFormSemantics.mediaRowMinHeight,
      verticalPadding: AppSpacing.intraGroupSm,
      trailing: _MediaPreview(
        source: _effectiveCover,
        isAvatar: false,
        previewKey: const ValueKey<String>('edit-profile-cover-preview'),
      ),
      onTap: () => unawaited(_pickMedia(_EditProfileMediaTarget.cover)),
    );
  }

  Widget _buildAvatarRow() {
    return ProfileIosGroupedCell(
      title: UITextConstants.editProfileAvatarLabel,
      minHeight: _EditProfileFormSemantics.mediaRowMinHeight,
      verticalPadding: AppSpacing.intraGroupSm,
      trailing: _MediaPreview(
        source: _effectiveAvatar,
        isAvatar: true,
        previewKey: const ValueKey<String>('edit-profile-avatar-preview'),
      ),
      onTap: () => unawaited(_pickMedia(_EditProfileMediaTarget.avatar)),
    );
  }
}
