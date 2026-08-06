/// Notifies other composed surfaces that the pending greeting projection
/// should be loaded again after a greeting command reaches a terminal state.
abstract interface class GreetingInboxRefresh {
  void refreshPendingInbox();
}
