import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/user_relationship_state.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/user_relationship_state.dart';
export 'package:quwoquan_app/runtime/di/user_relationship_state_storage_dependencies.dart';

final userRelationshipStateProvider =
    NotifierProvider<UserRelationshipStateNotifier, UserRelationshipState>(
      UserRelationshipStateNotifier.new,
    );
