import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_terminal_account_purgers.dart';

final class PostPublicationIntentLocalStorage
    implements PostPublicationIntentTerminalAccountPurger {
  const PostPublicationIntentLocalStorage.forTerminalAccountClosure(
    this._terminalActorId,
  );

  final String _terminalActorId;

  static String scopeKey(String? currentUserId) {
    final normalized = currentUserId?.trim() ?? '';
    return 'post_publication_intents:${normalized.isEmpty ? 'guest' : normalized}';
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

  @override
  Future<void> purgeForTerminalAccountClosure() =>
      clearForTerminalAccountClosure(_terminalActorId);
}
