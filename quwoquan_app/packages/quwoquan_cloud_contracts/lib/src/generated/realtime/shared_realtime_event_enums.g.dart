// Code generated from canonical _shared/types.yaml enums required by realtime payloads. DO NOT EDIT.

enum ConversationStatus {
  active("active"),
  dissolved("dissolved");

  const ConversationStatus(this.wireName);

  final String wireName;

  static ConversationStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => ConversationStatus.active,
      "dissolved" => ConversationStatus.dissolved,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MemberType {
  user("user"),
  assistant("assistant");

  const MemberType(this.wireName);

  final String wireName;

  static MemberType fromWire(Object? value, String path) {
    return switch (value) {
      "user" => MemberType.user,
      "assistant" => MemberType.assistant,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}
