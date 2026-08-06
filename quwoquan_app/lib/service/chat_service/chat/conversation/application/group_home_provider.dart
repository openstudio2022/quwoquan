import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

final groupHomeProvider = FutureProvider.family<GroupHome, String>((
  ref,
  conversationId,
) async {
  final repo = ref.watch(chatGroupAdminRepositoryProvider);
  return repo.getGroupHome(conversationId);
});
