part of "auth_session.dart";

class AuthSessionController extends Notifier<AuthSessionState> {
  static const Duration _staleRestoreRefreshThreshold = Duration(hours: 12);
  static const Duration _foregroundAuthCheckThreshold = Duration(hours: 24);
  static const Duration _startupRestoreReadBudget = Duration(seconds: 2);

  bool _restoreStarted = false;
  Future<bool>? _refreshInFlight;
  void Function()? _cancelPendingStartupRestore;

  AuthSessionStore get _store => ref.read(authSessionStoreProvider);

  @override
  AuthSessionState build() {
    ref.onDispose(_cancelStartupRestore);
    final restoreGateOpen = ref.watch(startupAuthRestoreGateProvider);
    if (restoreGateOpen && !_restoreStarted) {
      _restoreStarted = true;
      unawaited(restore());
    }
    return const AuthSessionState.restoring();
  }

  Future<void> restore() async {
    try {
      final stored = await _readStoredSessionWithinStartupBudget();
      _syncDeviceActorId(stored.installId);
      if (!ref.mounted) {
        return;
      }
      if (stored.accessToken.isNotEmpty &&
          stored.refreshToken.isNotEmpty &&
          stored.ownerId.isNotEmpty) {
        final authenticatedState = AuthSessionState(
          status: AuthSessionStatus.authenticated,
          accessToken: stored.accessToken,
          refreshToken: stored.refreshToken,
          ownerId: stored.ownerId,
          activeSubAccountId: stored.activeSubAccountId,
          accountState: stored.accountState,
          identityOrigin: stored.identityOrigin,
          installId: stored.installId,
          rememberedLoginMethod: stored.rememberedLoginMethod,
          rememberedLoginMaskedIdentifier:
              stored.rememberedLoginMaskedIdentifier,
          rememberedDisplayName: stored.rememberedDisplayName,
          rememberedAvatarUrl: stored.rememberedAvatarUrl,
          rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
        );
        state = authenticatedState;
        if (_shouldRefreshDuringRestore(stored)) {
          await refreshSessionIfNeeded(force: true);
        }
        return;
      }
      state = AuthSessionState(
        status: AuthSessionStatus.guest,
        promptReason: stored.launchPromptDismissed
            ? null
            : stored.manualLoggedOut
            ? AuthPromptReason.manualLoggedOut
            : AuthPromptReason.firstRun,
        installId: stored.installId,
        rememberedLoginMethod: stored.rememberedLoginMethod,
        rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
        rememberedDisplayName: stored.rememberedDisplayName,
        rememberedAvatarUrl: stored.rememberedAvatarUrl,
        rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = AuthSessionState(
        status: AuthSessionStatus.guest,
        promptReason: AuthPromptReason.sessionExpired,
        rememberedLoginMethod: state.rememberedLoginMethod,
        rememberedLoginMaskedIdentifier: state.rememberedLoginMaskedIdentifier,
        rememberedDisplayName: state.rememberedDisplayName,
        rememberedAvatarUrl: state.rememberedAvatarUrl,
        rememberedNicknameCustomized: state.rememberedNicknameCustomized,
        errorMessage: runtimeErrorDisplayMessage(e),
      );
    }
  }

  Future<StoredAuthSession> _readStoredSessionWithinStartupBudget() {
    final result = Completer<StoredAuthSession>();
    Timer? timeoutTimer;

    void completeValue(StoredAuthSession stored) {
      if (!result.isCompleted) {
        result.complete(stored);
      }
    }

    void completeError(Object error, StackTrace stackTrace) {
      if (!result.isCompleted) {
        result.completeError(error, stackTrace);
      }
    }

    void cancel() {
      timeoutTimer?.cancel();
      timeoutTimer = null;
      completeError(const _AuthSessionRestoreCancelled(), StackTrace.current);
    }

    _cancelPendingStartupRestore = cancel;
    try {
      _store.read().then<void>(
        completeValue,
        onError: (Object error, StackTrace stackTrace) {
          completeError(error, stackTrace);
        },
      );
      timeoutTimer = Timer(_startupRestoreReadBudget, () {
        completeError(
          TimeoutException(
            'Auth session restore exceeded $_startupRestoreReadBudget',
          ),
          StackTrace.current,
        );
      });
    } catch (error, stackTrace) {
      completeError(error, stackTrace);
    }

    return result.future.whenComplete(() {
      timeoutTimer?.cancel();
      timeoutTimer = null;
      if (identical(_cancelPendingStartupRestore, cancel)) {
        _cancelPendingStartupRestore = null;
      }
    });
  }

  void _cancelStartupRestore() {
    final cancel = _cancelPendingStartupRestore;
    _cancelPendingStartupRestore = null;
    cancel?.call();
  }

  Future<void> applyLoginGrant(AuthSessionGrant result) async {
    await _store.saveLoginGrant(result);
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
    );
  }

  Future<void> applyRememberedLoginGrant(
    AuthSessionGrant result, {
    required AuthRememberedLoginMethod rememberedLoginMethod,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    await _store.saveLoginGrant(
      result,
      rememberedLoginMethod: rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: rememberedLoginMaskedIdentifier,
      rememberedLoginIdentifier: rememberedLoginIdentifier,
    );
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
    );
  }

  Future<void> applyRefreshGrant(TokenRefreshGrant result) async {
    final current = state;
    final accessToken = result.accessToken.trim();
    final refreshToken = result.refreshToken.trim();
    if (accessToken.isEmpty || refreshToken.isEmpty) {
      throw StateError('refresh result missing tokens');
    }
    await _store.saveRefreshGrant(result);
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: accessToken,
      refreshToken: refreshToken,
      ownerId: current.ownerId.isNotEmpty ? current.ownerId : stored.ownerId,
      activeSubAccountId: current.activeSubAccountId.isNotEmpty
          ? current.activeSubAccountId
          : stored.activeSubAccountId,
      accountState: current.accountState.isNotEmpty
          ? current.accountState
          : stored.accountState,
      identityOrigin: current.identityOrigin.isNotEmpty
          ? current.identityOrigin
          : stored.identityOrigin,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
    );
  }

  Future<bool> refreshSessionIfNeeded({
    bool force = false,
    Future<void>? abortTrigger,
  }) async {
    final current = state;
    if (!current.isAuthenticated || current.refreshToken.trim().isEmpty) {
      return false;
    }
    if (!force && _refreshInFlight != null) {
      return _awaitRefresh(_refreshInFlight!, abortTrigger: abortTrigger);
    }
    final future = _performRefresh(abortTrigger: abortTrigger);
    _refreshInFlight = future;
    try {
      return await _awaitRefresh(future, abortTrigger: abortTrigger);
    } finally {
      if (identical(_refreshInFlight, future)) {
        _refreshInFlight = null;
      }
    }
  }

  Future<bool> refreshIfSessionLooksStale() async {
    final stored = await _store.read();
    if (!_shouldRefreshForForegroundCheck(stored)) {
      return false;
    }
    return refreshSessionIfNeeded(force: true);
  }

  Future<void> markForegroundAuthCheck() async {
    await _store.markForegroundAuthCheckNow();
  }

  Future<void> continueAsGuest({AuthPromptReason? reason}) async {
    await _store.markLaunchPromptDismissed();
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: reason,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
    );
  }

  /// 软退出（默认）：仅失效当前活跃会话，保留快速登录凭证与账号摘要。
  ///
  /// 有效期内（云端下发，默认 30 天）再次打开登录页可一键免验证码快速登录。
  /// 调用方（settings）须保证不向远端吊销 refresh token。
  Future<void> softLogout() async {
    await _store.softLogout();
    final stored = await _store.read();
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.manualLoggedOut,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
    );
  }

  /// 彻底退出：清除本机全部登录凭证。调用方负责向远端吊销 refresh token。
  /// 下次登录必须重新验证（无可用快速登录凭证）。
  Future<void> hardLogout() async {
    await _store.clearSession(manualLogout: true);
    final stored = await _store.read();
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.manualLoggedOut,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
    );
  }

  /// 云端账号已进入不可逆 closed 终态后，本地持久层即使异常也必须立即切到游客态。
  ///
  /// 该方法不替代 [hardLogout]；仅供 CloseAccount 已成功、但本地安全存储清理失败时
  /// fail-closed，避免失效 token 继续驱动已登录 UI 或形成登录门循环。
  void forceGuestAfterTerminalAccountClosure() {
    if (!ref.mounted) {
      return;
    }
    final installId = state.installId;
    _syncDeviceActorId(installId);
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.manualLoggedOut,
      installId: installId,
    );
  }

  /// 兼容旧调用：等价于彻底退出。新代码应显式使用 softLogout / hardLogout。
  Future<void> clearForLogout() => hardLogout();

  Future<void> clearForExpiredSession() async {
    await _store.clearSession(manualLogout: false);
    final stored = await _store.read();
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.sessionExpired,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
    );
  }

  /// 账号被服务端限制时清除所有可换发凭证，并保留结构化的受限原因供路由切到
  /// 安全首页。不得将它降级成普通 sessionExpired，否则用户看不到受限说明且
  /// 可能回到会再次触发登录门的目标页面。
  Future<void> clearForSuspendedAccount({required String errorMessage}) async {
    await _store.clearSession(manualLogout: false);
    final stored = await _store.read();
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.accountSuspended,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
      errorMessage: errorMessage,
    );
  }

  /// 服务端确认账号 closed 时清除全部凭据，并保留终态信号供本地隐私清理恢复器消费。
  Future<void> clearForClosedAccount({required String errorMessage}) async {
    await _store.clearSession(manualLogout: true);
    final stored = await _store.read();
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.accountClosed,
      installId: stored.installId,
      errorMessage: errorMessage,
    );
  }

  Future<void> updateActiveSubAccount(String subAccountId) async {
    await _store.updateActiveSubAccount(subAccountId);
    state = state.copyWith(activeSubAccountId: subAccountId.trim());
  }

  Future<bool> _performRefresh({Future<void>? abortTrigger}) async {
    final current = state;
    final refreshToken = current.refreshToken.trim();
    if (!current.isAuthenticated || refreshToken.isEmpty) {
      return false;
    }
    try {
      final result = await _awaitRefreshResult(
        ref
            .read(accountSessionLifecycleCommandWriterProvider)
            .refreshToken(RefreshTokenCommand(refreshToken: refreshToken)),
        abortTrigger: abortTrigger,
      );
      await applyRefreshGrant(result);
      return true;
    } catch (e) {
      if (e is http.RequestAbortedException ||
          e is CloudOperationCancelledException) {
        return false;
      }
      if (_isAccountDeletedFailure(e)) {
        await _saveTerminalCleanupReceipt(current);
        await clearForClosedAccount(
          errorMessage: runtimeErrorDisplayMessage(e),
        );
        return false;
      }
      if (_isAccountSuspendedFailure(e)) {
        await clearForSuspendedAccount(
          errorMessage: runtimeErrorDisplayMessage(e),
        );
        return false;
      }
      if (_shouldClearSessionForRefreshFailure(e)) {
        await clearForExpiredSession();
        if (!ref.mounted) {
          return false;
        }
        state = state.copyWith(
          errorMessage: () => runtimeErrorDisplayMessage(e),
        );
        return false;
      }
      await _store.markForegroundAuthCheckNow();
      if (!ref.mounted) {
        return false;
      }
      state = state.copyWith(errorMessage: () => runtimeErrorDisplayMessage(e));
      return false;
    }
  }

  Future<TokenRefreshGrant> _awaitRefreshResult(
    Future<TokenRefreshGrant> refresh, {
    Future<void>? abortTrigger,
  }) {
    if (abortTrigger == null) {
      return refresh;
    }
    return Future.any<TokenRefreshGrant>(<Future<TokenRefreshGrant>>[
      refresh,
      abortTrigger.then<TokenRefreshGrant>(
        (_) => throw const CloudOperationCancelledException(),
      ),
    ]);
  }

  Future<bool> _awaitRefresh(
    Future<bool> refresh, {
    Future<void>? abortTrigger,
  }) {
    if (abortTrigger == null) {
      return refresh;
    }
    return Future.any<bool>(<Future<bool>>[
      refresh,
      abortTrigger.then((_) => false),
    ]);
  }

  bool _shouldClearSessionForRefreshFailure(Object error) {
    if (error is AccountSessionTokenExpiredException) {
      return true;
    }
    if (error is CloudException) {
      return error.code == UserErrorCode.accountDeleted.code ||
          error.code == UserErrorCode.tokenStale.code ||
          error.type == CloudErrorType.unauthorized ||
          error.type == CloudErrorType.forbidden;
    }
    if (error is StateError) {
      return true;
    }
    return false;
  }

  bool _isAccountSuspendedFailure(Object error) {
    return error is CloudException &&
        error.code == UserErrorCode.accountSuspended.code;
  }

  bool _isAccountDeletedFailure(Object error) {
    return error is CloudException &&
        error.code == UserErrorCode.accountDeleted.code;
  }

  Future<void> _saveTerminalCleanupReceipt(AuthSessionState session) async {
    try {
      await ref
          .read(terminalAccountCleanupReceiptStoreProvider)
          .save(
            TerminalAccountCleanupReceipt(
              accountId: session.ownerId,
              personaId: session.activeSubAccountId,
              installId: session.installId,
            ),
          );
    } catch (error, stackTrace) {
      developer.log(
        'terminal account cleanup receipt persistence failed',
        name: 'AuthSessionController',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  bool _shouldRefreshDuringRestore(StoredAuthSession stored) {
    return _isOlderThan(
      stored.lastRefreshAtEpochMs,
      _staleRestoreRefreshThreshold,
    );
  }

  bool _shouldRefreshForForegroundCheck(StoredAuthSession stored) {
    if (stored.accessToken.isEmpty ||
        stored.refreshToken.isEmpty ||
        stored.ownerId.isEmpty) {
      return false;
    }
    return _isOlderThan(
      stored.lastForegroundAuthCheckAtEpochMs,
      _foregroundAuthCheckThreshold,
    );
  }

  bool _isOlderThan(int epochMs, Duration threshold) {
    if (epochMs <= 0) {
      return true;
    }
    final now = DateTime.now().millisecondsSinceEpoch;
    return now - epochMs >= threshold.inMilliseconds;
  }
}

final class _AuthSessionRestoreCancelled implements Exception {
  const _AuthSessionRestoreCancelled();
}
