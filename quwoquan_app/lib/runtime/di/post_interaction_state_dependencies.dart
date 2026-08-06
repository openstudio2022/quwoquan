import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_interaction_state.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_interaction_state.dart';

final postInteractionStateProvider =
    NotifierProvider<PostInteractionStateNotifier, PostInteractionState>(
      PostInteractionStateNotifier.new,
    );
