import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/emoji/emoji_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

final _sharedPreferencesProvider = FutureProvider<SharedPreferences>((ref) {
  return SharedPreferences.getInstance();
});

final emojiRepositoryProvider = FutureProvider<EmojiRepository>((ref) async {
  final prefs = await ref.watch(_sharedPreferencesProvider.future);
  return EmojiRepository(prefs);
});
