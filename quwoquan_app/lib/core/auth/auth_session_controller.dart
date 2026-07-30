part of "auth_session.dart";

class AuthSessionController extends Notifier<AuthSessionState> {
  static const Duration _staleRestoreRefreshThreshold = Duration(hours: 12);
  static const Duration _foregroundAuthCheckThreshold = Duration(hours: 24);
  static const Duration _startupRestoreReadBudget = Duration(seconds: 2);
  static const Duration _proactiveAccessTokenRefreshLead = Duration(minutes: 2);
  static const Duration _proactiveRefreshRetryCooldown = Duration(seconds: 30);

  bool _restoreStarted = false;
  Future<void>? _restoreInFlight;
  Future<bool>? _anonymousBootstrapInFlight;
  Future<bool>? _refreshInFlight;
  void Function()? _cancelPendingStartupRestore;
  Object? _lastTrustedSessionFailure;
  StackTrace? _lastTrustedSessionFailureStack;
  DateTime? _lastProactiveRefreshAttemptAt;
  int _explicitLoginGeneration = 0;
  Future<void> _sessionMutationTail = Future<void>.value();

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

  Future<void> restore() {
    final inFlight = _restoreInFlight;
    if (inFlight != null) {
      return inFlight;
    }
    late final Future<void> restore;
    restore = _performRestore().whenComplete(() {
      if (identical(_restoreInFlight, restore)) {
        _restoreInFlight = null;
      }
    });
    _restoreInFlight = restore;
    return restore;
  }

  Future<void> _performRestore() async {
    try {
      final stored = await _readStoredSessionWithinStartupBudget();
      _syncDeviceActorId(stored.installId);
      if (!ref.mounted) {
        return;
      }
      if (stored.hasCompleteActiveSession) {
        state = _stateFromStoredSession(stored);
        if (_shouldRefreshDuringRestore(stored)) {
          await refreshSessionIfNeeded(force: true);
        }
        return;
      }
      state = _guestStateFromStored(stored);
      await ensureTrustedGuestSession(knownStored: stored);
    } catch (error, stackTrace) {
      _rememberTrustedSessionFailure(error, stackTrace);
      if (!ref.mounted) {
        return;
      }
      state = AuthSessionState(
        status: AuthSessionStatus.guest,
        promptReason: AuthPromptReason.sessionExpired,
        installId: state.installId,
        rememberedLoginMethod: state.rememberedLoginMethod,
        rememberedLoginMaskedIdentifier: state.rememberedLoginMaskedIdentifier,
        rememberedDisplayName: state.rememberedDisplayName,
        rememberedAvatarUrl: state.rememberedAvatarUrl,
        rememberedNicknameCustomized: state.rememberedNicknameCustomized,
        errorMessage: runtimeErrorDisplayMessage(error),
      );
    }
  }

  /// 为普通 Remote 请求提供可信 bearer。
  ///
  /// 安全启动面不等待该 Future；业务请求会等待既有 session restore 或一次
  /// `LoginAnonymous`。bootstrap 失败会把同一结构化错误交给请求链，而不是退回裸
  /// `X-Client-Device-Actor-Id` 后得到伪成功空列表。
  Future<String?> accessTokenForRequest() async {
    final restore = _restoreInFlight;
    if (restore != null) {
      await restore;
    }
    if (state.hasTrustedSession) {
      await _refreshAccessTokenBeforeExpiryIfNeeded();
      final token = state.accessToken.trim();
      if (state.hasTrustedSession && token.isNotEmpty) {
        return token;
      }
    }
    final previousFailure = _takeTrustedSessionFailure();
    if (previousFailure != null) {
      Error.throwWithStackTrace(previousFailure.$1, previousFailure.$2);
    }
    try {
      await ensureTrustedGuestSession();
    } catch (_) {
      // 本次请求已经直接收到 bootstrap 原始异常，避免下一请求再次消费同一失败。
      _takeTrustedSessionFailure();
      rethrow;
    }
    final token = state.accessToken.trim();
    if (!state.hasTrustedSession || token.isEmpty) {
      throw StateError('trusted guest session bootstrap produced no session');
    }
    return token;
  }

  /// 首次安装、会话清理或匿名 token 失效后的单飞 bootstrap。
  Future<bool> ensureTrustedGuestSession({StoredAuthSession? knownStored}) {
    if (state.hasTrustedSession) {
      return Future<bool>.value(true);
    }
    final inFlight = _anonymousBootstrapInFlight;
    if (inFlight != null) {
      return inFlight;
    }
    _lastTrustedSessionFailure = null;
    _lastTrustedSessionFailureStack = null;
    late final Future<bool> bootstrap;
    bootstrap = _performTrustedGuestBootstrap(knownStored: knownStored)
        .whenComplete(() {
          if (identical(_anonymousBootstrapInFlight, bootstrap)) {
            _anonymousBootstrapInFlight = null;
          }
        });
    _anonymousBootstrapInFlight = bootstrap;
    return bootstrap;
  }

  Future<bool> _performTrustedGuestBootstrap({
    StoredAuthSession? knownStored,
  }) async {
    try {
      final stored = knownStored ?? await _store.read();
      _syncDeviceActorId(stored.installId);
      if (!ref.mounted) {
        return false;
      }
      if (stored.hasCompleteActiveSession) {
        state = _stateFromStoredSession(stored);
        return true;
      }
      final installId = stored.installId.trim();
      final fingerprint = deriveAnonymousDeviceFingerprintHash(installId);
      if (installId.isEmpty || fingerprint.isEmpty) {
        throw StateError('anonymous bootstrap requires install identity');
      }
      final explicitLoginGeneration = _explicitLoginGeneration;
      final result = await ref
          .read(accountSessionLoginCommandWriterProvider)
          .loginAnonymous(
            LoginAnonymousCommand(
              installId: installId,
              deviceFingerprintHash: fingerprint,
              platform: CloudRequestHeaders.platform(),
              appVersion: CloudRequestHeaders.appVersion,
            ),
          );
      _validateAnonymousGrant(result);
      return _runSessionMutation<bool>(() async {
        if (_explicitLoginGeneration != explicitLoginGeneration ||
            state.isAuthenticated) {
          return state.hasTrustedSession;
        }
        await _store.saveLoginGrant(
          result,
          rememberedLoginMethod: AuthRememberedLoginMethod.anonymous,
        );
        final persisted = await _store.read();
        _syncDeviceActorId(persisted.installId);
        if (!ref.mounted) {
          return false;
        }
        if (_explicitLoginGeneration != explicitLoginGeneration ||
            state.isAuthenticated) {
          return state.hasTrustedSession;
        }
        state = _trustedGuestStateFromStored(persisted);
        return true;
      });
    } catch (error, stackTrace) {
      _rememberTrustedSessionFailure(error, stackTrace);
      if (ref.mounted && !state.isAuthenticated) {
        state = state.copyWith(
          status: AuthSessionStatus.guest,
          errorMessage: () => runtimeErrorDisplayMessage(error),
        );
      }
      rethrow;
    }
  }

  void _validateAnonymousGrant(AuthSessionGrant result) {
    if (result.accessToken.trim().isEmpty ||
        result.refreshToken.trim().isEmpty ||
        result.ownerId.trim().isEmpty ||
        (result.activePersona?.personaId.trim() ?? '').isEmpty) {
      throw StateError('anonymous login returned an incomplete session grant');
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
    _explicitLoginGeneration += 1;
    await _runSessionMutation<void>(() async {
      await _store.saveLoginGrant(result);
      final stored = await _store.read();
      _syncDeviceActorId(stored.installId);
      if (!ref.mounted) {
        return;
      }
      state = _stateFromStoredSession(stored);
    });
  }

  Future<void> applyTrustedGuestGrant(AuthSessionGrant result) async {
    _validateAnonymousGrant(result);
    await _runSessionMutation<void>(() async {
      await _store.saveLoginGrant(
        result,
        rememberedLoginMethod: AuthRememberedLoginMethod.anonymous,
      );
      final stored = await _store.read();
      _syncDeviceActorId(stored.installId);
      if (!ref.mounted) {
        return;
      }
      state = _trustedGuestStateFromStored(stored);
    });
  }

  Future<void> applyRememberedLoginGrant(
    AuthSessionGrant result, {
    required AuthRememberedLoginMethod rememberedLoginMethod,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    _explicitLoginGeneration += 1;
    await _runSessionMutation<void>(() async {
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
      state = _authenticatedStateFromStored(stored);
    });
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
      status: current.isGuest
          ? AuthSessionStatus.guest
          : AuthSessionStatus.authenticated,
      accessToken: accessToken,
      refreshToken: refreshToken,
      ownerId: current.ownerId.isNotEmpty ? current.ownerId : stored.ownerId,
      activePersonaId: current.activePersonaId.isNotEmpty
          ? current.activePersonaId
          : stored.activePersonaId,
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
    if (!current.hasTrustedSession || current.refreshToken.trim().isEmpty) {
      return false;
    }
    final inFlight = _refreshInFlight;
    if (inFlight != null) {
      // refresh token 每次换发都会 rotation。即使调用方要求 force，也必须加入
      // 已在执行的请求，禁止同一旧 token 并发换发导致 lineage 被误判为重放。
      return _awaitRefresh(inFlight, abortTrigger: abortTrigger);
    }
    // A caller may stop waiting, but it must never cancel or retire the shared
    // refresh itself: the refresh token rotates once server-side. Clearing the
    // singleflight slot before that request settles would let a later caller
    // replay the old token concurrently.
    final future = _performRefresh();
    _refreshInFlight = future;
    unawaited(
      future.then<void>(
        (_) {
          if (identical(_refreshInFlight, future)) {
            _refreshInFlight = null;
          }
        },
        onError: (Object _, StackTrace _) {
          if (identical(_refreshInFlight, future)) {
            _refreshInFlight = null;
          }
        },
      ),
    );
    return _awaitRefresh(future, abortTrigger: abortTrigger);
  }

  Future<bool> refreshIfSessionLooksStale() async {
    final stored = await _store.read();
    if (!_shouldRefreshForForegroundCheck(stored)) {
      return false;
    }
    return refreshSessionIfNeeded(force: true);
  }

  Future<void> _refreshAccessTokenBeforeExpiryIfNeeded() async {
    final current = state;
    if (!current.hasTrustedSession || current.refreshToken.trim().isEmpty) {
      return;
    }
    final expiry = _accessTokenExpiryForScheduling(current.accessToken);
    if (expiry == null) {
      // 无法解析的 token 不用于客户端授权或过期推断；服务端仍是有效性的唯一裁判。
      return;
    }
    final now = DateTime.now().toUtc();
    if (expiry.isAfter(now.add(_proactiveAccessTokenRefreshLead))) {
      return;
    }

    final inFlight = _refreshInFlight;
    if (inFlight != null) {
      await inFlight;
      return;
    }
    final lastAttempt = _lastProactiveRefreshAttemptAt;
    if (lastAttempt != null &&
        now.difference(lastAttempt) < _proactiveRefreshRetryCooldown) {
      return;
    }
    _lastProactiveRefreshAttemptAt = now;
    await refreshSessionIfNeeded(force: true);
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
    state = stored.hasCompleteActiveSession
        ? _trustedGuestStateFromStored(stored, promptReason: reason)
        : _guestStateFromStored(stored, promptReason: reason);
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

  /// Applies a canonical account-state failure observed on a generated
  /// Gateway request to the local session.
  ///
  /// The request's bearer is mandatory: an old request may complete after an
  /// approved restore and a new login, and that late response must not clear
  /// the newer session. Serialization with login/session writes closes the
  /// remaining race between the token comparison and secure-storage cleanup.
  Future<void> handleAuthoritativeSessionFailure(
    CloudException failure, {
    required String presentedAccessToken,
  }) {
    return _runSessionMutation<void>(() async {
      final requestToken = presentedAccessToken.trim();
      final current = state;
      if (requestToken.isEmpty || current.accessToken.trim() != requestToken) {
        return;
      }
      final suspended = failure.code == UserErrorCode.accountSuspended.code;
      final closed = failure.code == UserErrorCode.accountDeleted.code;
      if (!suspended && !closed) {
        return;
      }

      if (closed) {
        await _saveTerminalCleanupReceipt(current);
      }
      StoredAuthSession? stored;
      try {
        await _store.clearSession(manualLogout: closed);
        stored = await _store.read();
      } catch (error, stackTrace) {
        // The in-memory authority must still fail closed. A later launch will
        // present the stale bearer to the server again and retry canonical
        // cleanup; no raw failure reaches the restricted surface.
        developer.log(
          'authoritative account-state session cleanup failed',
          name: 'AuthSessionController',
          error: error,
          stackTrace: stackTrace,
        );
      }
      if (!ref.mounted || state.accessToken.trim() != requestToken) {
        return;
      }
      final safeInstallId = stored?.installId ?? current.installId;
      _syncDeviceActorId(safeInstallId);
      state = AuthSessionState(
        status: AuthSessionStatus.guest,
        promptReason: suspended
            ? AuthPromptReason.accountSuspended
            : AuthPromptReason.accountClosed,
        installId: safeInstallId,
        rememberedLoginMethod: suspended
            ? (stored?.rememberedLoginMethod ?? current.rememberedLoginMethod)
            : AuthRememberedLoginMethod.unknown,
        rememberedLoginMaskedIdentifier: suspended
            ? (stored?.rememberedLoginMaskedIdentifier ??
                  current.rememberedLoginMaskedIdentifier)
            : '',
        rememberedDisplayName: suspended
            ? (stored?.rememberedDisplayName ?? current.rememberedDisplayName)
            : '',
        rememberedAvatarUrl: suspended
            ? (stored?.rememberedAvatarUrl ?? current.rememberedAvatarUrl)
            : '',
        rememberedNicknameCustomized: suspended
            ? (stored?.rememberedNicknameCustomized ??
                  current.rememberedNicknameCustomized)
            : false,
        errorMessage: runtimeErrorDisplayMessage(failure),
      );
    });
  }

  /// Acknowledges the safe account-restriction explanation before routing to
  /// the public home. This only clears the presentation signal; all bearer and
  /// refresh credentials remain physically cleared.
  void acknowledgeAccountRestrictionNotice() {
    if (state.promptReason != AuthPromptReason.accountSuspended) {
      return;
    }
    state = state.copyWith(promptReason: () => null, errorMessage: () => null);
    unawaited(
      _store.markLaunchPromptDismissed().catchError((
        Object error,
        StackTrace stackTrace,
      ) {
        developer.log(
          'account restriction notice acknowledgement persistence failed',
          name: 'AuthSessionController',
          error: error,
          stackTrace: stackTrace,
        );
      }),
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

  Future<void> updateActivePersona(String personaId) async {
    await _store.updateActivePersona(personaId);
    state = state.copyWith(activePersonaId: personaId.trim());
  }

  Future<bool> _performRefresh() async {
    final current = state;
    final refreshToken = current.refreshToken.trim();
    if (!current.hasTrustedSession || refreshToken.isEmpty) {
      return false;
    }
    try {
      final result = await ref
          .read(accountSessionLifecycleCommandWriterProvider)
          .refreshToken(RefreshTokenCommand(refreshToken: refreshToken));
      if (!ref.mounted ||
          !state.hasTrustedSession ||
          state.refreshToken.trim() != refreshToken ||
          state.ownerId != current.ownerId) {
        // Logout, account replacement, or another authoritative session
        // mutation won while the network request was in flight. Its state is
        // newer than this grant, so the late result must not resurrect it.
        return false;
      }
      await applyRefreshGrant(result);
      return true;
    } catch (e) {
      if (e is http.RequestAbortedException ||
          e is CloudOperationCancelledException) {
        return false;
      }
      if (!ref.mounted ||
          state.refreshToken.trim() != refreshToken ||
          state.ownerId != current.ownerId) {
        // A newer login/logout/session mutation already won. A delayed error
        // from the old refresh lineage cannot demote the newer session.
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
              personaId: session.activePersonaId,
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

  AuthSessionState _stateFromStoredSession(StoredAuthSession stored) {
    if (stored.isAnonymousSession) {
      return _trustedGuestStateFromStored(stored);
    }
    return _authenticatedStateFromStored(stored);
  }

  AuthSessionState _authenticatedStateFromStored(StoredAuthSession stored) {
    return AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activePersonaId: stored.activePersonaId,
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

  AuthSessionState _trustedGuestStateFromStored(
    StoredAuthSession stored, {
    AuthPromptReason? promptReason,
  }) {
    return AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: promptReason ?? _guestPromptReason(stored),
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activePersonaId: stored.activePersonaId,
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

  AuthSessionState _guestStateFromStored(
    StoredAuthSession stored, {
    AuthPromptReason? promptReason,
  }) {
    return AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: promptReason ?? _guestPromptReason(stored),
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
    );
  }

  AuthPromptReason? _guestPromptReason(StoredAuthSession stored) {
    if (stored.launchPromptDismissed) {
      return null;
    }
    return stored.manualLoggedOut
        ? AuthPromptReason.manualLoggedOut
        : AuthPromptReason.firstRun;
  }

  Future<T> _runSessionMutation<T>(Future<T> Function() mutation) {
    final result = Completer<T>();
    final previous = _sessionMutationTail;
    _sessionMutationTail = () async {
      try {
        await previous;
      } catch (_) {
        // 前一项失败不能永久锁死会话持久化队列。
      }
      try {
        result.complete(await mutation());
      } catch (error, stackTrace) {
        result.completeError(error, stackTrace);
      }
    }();
    return result.future;
  }

  void _rememberTrustedSessionFailure(Object error, StackTrace stackTrace) {
    _lastTrustedSessionFailure = error;
    _lastTrustedSessionFailureStack = stackTrace;
    final cloudErrorCode = error is CloudException ? error.code?.trim() : null;
    final code = cloudErrorCode == null || cloudErrorCode.isEmpty
        ? error.runtimeType.toString()
        : cloudErrorCode;
    developer.log(
      'trusted guest session unavailable code=$code',
      name: 'AuthSessionController',
    );
  }

  (Object, StackTrace)? _takeTrustedSessionFailure() {
    final error = _lastTrustedSessionFailure;
    if (error == null) {
      return null;
    }
    final stackTrace = _lastTrustedSessionFailureStack ?? StackTrace.current;
    _lastTrustedSessionFailure = null;
    _lastTrustedSessionFailureStack = null;
    return (error, stackTrace);
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

/// 只读取 JWT `exp` 作为主动刷新调度提示；不验证签名，也绝不据此授予权限。
DateTime? _accessTokenExpiryForScheduling(String token) {
  try {
    final segments = token.trim().split('.');
    if (segments.length != 3 || segments[1].isEmpty) {
      return null;
    }
    final payload = jsonDecode(
      utf8.decode(base64Url.decode(base64Url.normalize(segments[1]))),
    );
    if (payload is! Map<String, dynamic>) {
      return null;
    }
    final rawExpiry = payload['exp'];
    final expirySeconds = switch (rawExpiry) {
      int value => value,
      num value => value.toInt(),
      String value => int.tryParse(value),
      _ => null,
    };
    if (expirySeconds == null || expirySeconds <= 0) {
      return null;
    }
    return DateTime.fromMillisecondsSinceEpoch(
      expirySeconds * Duration.millisecondsPerSecond,
      isUtc: true,
    );
  } catch (_) {
    return null;
  }
}
