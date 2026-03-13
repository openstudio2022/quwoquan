import 'package:flutter/foundation.dart';

enum EditorStartAction { gallery, write, capture }

enum CreateContentIdentity { moment, work }

extension CreateContentIdentityX on CreateContentIdentity {
  String get value => name;

  String get label => this == CreateContentIdentity.moment ? '点滴' : '作品';
}

@immutable
class IdentitySuggestion {
  const IdentitySuggestion({required this.identity, required this.reason});

  final CreateContentIdentity identity;
  final String reason;
}

@immutable
class CreateDraft {
  const CreateDraft({
    required this.id,
    required this.tabKey,
    required this.updatedAtMs,
    required this.identity,
    required this.data,
  });

  final String id;
  final String tabKey;
  final int updatedAtMs;
  final CreateContentIdentity identity;
  final Map<String, dynamic> data;

  factory CreateDraft.fromStorageMap(Map<String, dynamic> map) {
    final tabKey = (map['type'] ?? 'moment').toString();
    final identityName = (map['identity'] ?? '').toString().trim();
    final identity = _resolveIdentity(
      identityName: identityName,
      tabKey: tabKey,
    );
    return CreateDraft(
      id: (map['id'] ?? '').toString(),
      tabKey: tabKey,
      updatedAtMs: (map['updatedAt'] as num?)?.toInt() ?? 0,
      identity: identity,
      data: Map<String, dynamic>.from(
        map['data'] as Map? ?? const <String, dynamic>{},
      ),
    );
  }

  Map<String, dynamic> toStorageMap() => <String, dynamic>{
    'id': id,
    'type': tabKey,
    'updatedAt': updatedAtMs,
    'identity': identity.value,
    'data': data,
  };

  String get previewText {
    final content =
        (data['content'] ?? data['title'] ?? data['description'] ?? '')
            .toString()
            .trim();
    return content;
  }

  static CreateContentIdentity _resolveIdentity({
    required String identityName,
    required String tabKey,
  }) {
    if (identityName == CreateContentIdentity.work.value) {
      return CreateContentIdentity.work;
    }
    if (identityName == CreateContentIdentity.moment.value) {
      return CreateContentIdentity.moment;
    }
    switch (tabKey) {
      case 'photo':
      case 'video':
      case 'article':
        return CreateContentIdentity.work;
      default:
        return CreateContentIdentity.moment;
    }
  }
}
