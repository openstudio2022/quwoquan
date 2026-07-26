import 'package:shared_preferences/shared_preferences.dart';

final class PostPublicationIntentLocalStorage {
  const PostPublicationIntentLocalStorage._();

  static String scopeKey(String? currentUserId) {
    final normalized = currentUserId?.trim() ?? '';
    return 'post_publication_intents_v1:${normalized.isEmpty ? 'guest' : normalized}';
  }

  static Future<void> clearForTerminalAccountClosure(
    String currentUserId,
  ) async {
    final normalized = currentUserId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(
        currentUserId,
        'currentUserId',
        'terminal account closure requires an authenticated actor',
      );
    }
    final preferences = await SharedPreferences.getInstance();
    final key = scopeKey(normalized);
    await preferences.remove(key);
    if (preferences.containsKey(key)) {
      throw StateError('post publication intent cleanup verification failed');
    }
  }
}
