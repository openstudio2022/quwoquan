// Code generated from contracts/metadata/user/user_profile/fields.yaml. DO NOT EDIT.

import 'package:quwoquan_app/cloud/runtime/generated/user/user_profile_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_setting_dto.g.dart';

class UserFullSnapshotDto {
  final UserProfileDto profile;
  final PersonaDto? activePersona;
  final UserSettingDto? settings;

  const UserFullSnapshotDto({
    required this.profile,
    this.activePersona,
    this.settings,
  });

  factory UserFullSnapshotDto.fromJson(Map<String, dynamic> json) {
    return UserFullSnapshotDto(
      profile: UserProfileDto.fromJson(json['profile'] as Map<String, dynamic>),
      activePersona: json['activePersona'] != null
          ? PersonaDto.fromJson(json['activePersona'] as Map<String, dynamic>)
          : null,
      settings: json['settings'] != null
          ? UserSettingDto.fromJson(json['settings'] as Map<String, dynamic>)
          : null,
    );
  }

  Map<String, dynamic> toJson() => {
        'profile': profile.toJson(),
        if (activePersona != null) 'activePersona': activePersona!.toJson(),
        if (settings != null) 'settings': settings!.toJson(),
      };
}
