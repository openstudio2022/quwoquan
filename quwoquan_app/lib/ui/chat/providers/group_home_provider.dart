import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/group_home_dto.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

final groupHomeProvider = FutureProvider.family<GroupHomeDto, String>((
  ref,
  conversationId,
) async {
  final repo = ref.watch(chatGroupAdminRepositoryProvider);
  return repo.getGroupHome(conversationId);
});
