import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:record/record.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/core/platform/startup_deferred_plugins.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';

/// 应用内统一权限种类。
enum AppPermissionKind {
  microphone,
  camera,
  photos,
  location,
  contacts,
  notifications,
}

/// 权限所处阶段（对 UI 透明，屏蔽 iOS/Android 差异）。
enum AppPermissionPhase { granted, requestable, settingsRequired, restricted }

/// 权限请求触达面：JIT 动作 vs 整页能力。
enum AppPermissionSurface { jit, page }

/// [AppPermissionCoordinator.ensure] 结果。
enum AppPermissionEnsureOutcome {
  granted,
  denied,
  settingsRequired,
  restricted,
  softDenied,
}

typedef PermissionPhaseReader = Future<AppPermissionPhase> Function();
typedef PermissionRequester = Future<bool> Function();
typedef PermissionGrantChecker = Future<bool> Function();
typedef PermissionPrimerChecker = Future<bool> Function();
typedef PermissionPrimerMarker = Future<void> Function();
typedef PermissionSettingsOpener = Future<bool> Function();

class AppPermissionCopy {
  const AppPermissionCopy({
    required this.label,
    required this.primerTitle,
    required this.primerMessage,
    required this.settingsPathMessage,
    required this.deniedMessage,
  });

  final String label;
  final String primerTitle;
  final String primerMessage;
  final String settingsPathMessage;
  final String deniedMessage;
}

class AppPermissionSessionState {
  bool suppressSettingsPrompt = false;
  bool settingsVisitPending = false;
  void Function(bool granted)? onSettingsReturn;
}

/// 跨平台权限协调：系统 request 优先，设置跳转兜底，会话级 suppress 防死循环。
class AppPermissionCoordinator with WidgetsBindingObserver {
  AppPermissionCoordinator._();

  static final AppPermissionCoordinator instance = AppPermissionCoordinator._();

  @visibleForTesting
  factory AppPermissionCoordinator.createForTest() =>
      AppPermissionCoordinator._();

  @visibleForTesting
  AppPermissionSessionState testSession(AppPermissionKind kind) =>
      _sessionFor(kind);

  @visibleForTesting
  Future<void> handleSettingsReturnForTest() => _handleSettingsReturn();

  @visibleForTesting
  static AppPermissionCoordinator? debugInstance;

  static AppPermissionCoordinator get current => debugInstance ?? instance;

  @visibleForTesting
  static AppPermissionCoordinator get testable => debugInstance ?? instance;

  final Map<AppPermissionKind, AppPermissionSessionState> _sessions =
      <AppPermissionKind, AppPermissionSessionState>{};

  bool _lifecycleAttached = false;
  BuildContext? _toastContext;

  @visibleForTesting
  final Map<AppPermissionKind, PermissionPhaseReader> phaseReaders =
      <AppPermissionKind, PermissionPhaseReader>{};

  @visibleForTesting
  final Map<AppPermissionKind, PermissionRequester> requesters =
      <AppPermissionKind, PermissionRequester>{};

  @visibleForTesting
  final Map<AppPermissionKind, PermissionGrantChecker> grantCheckers =
      <AppPermissionKind, PermissionGrantChecker>{};

  @visibleForTesting
  final Map<AppPermissionKind, PermissionPrimerChecker> primerCheckers =
      <AppPermissionKind, PermissionPrimerChecker>{};

  @visibleForTesting
  final Map<AppPermissionKind, PermissionPrimerMarker> primerMarkers =
      <AppPermissionKind, PermissionPrimerMarker>{};

  @visibleForTesting
  PermissionSettingsOpener settingsOpener = openAppSettings;

  static const Map<AppPermissionKind, String> _primerPrefsKeys =
      <AppPermissionKind, String>{
        AppPermissionKind.microphone: 'app_permission_primer_mic_v1',
        AppPermissionKind.camera: 'app_permission_primer_camera_v1',
        AppPermissionKind.photos: 'app_permission_primer_photos_v1',
        AppPermissionKind.location: 'app_permission_primer_location_v1',
        AppPermissionKind.contacts: 'app_permission_primer_contacts_v1',
        AppPermissionKind.notifications:
            'app_permission_primer_notifications_v1',
      };

  void ensureLifecycleAttached() {
    if (_lifecycleAttached) {
      return;
    }
    WidgetsBinding.instance.addObserver(this);
    _lifecycleAttached = true;
    _registerDefaultAdapters();
  }

  void bindToastContext(BuildContext? context) {
    _toastContext = context;
  }

  void clearSession() {
    _sessions.clear();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) {
      return;
    }
    unawaited(_handleSettingsReturn());
  }

  AppPermissionCopy copyFor(AppPermissionKind kind) {
    return switch (kind) {
      AppPermissionKind.microphone => const AppPermissionCopy(
        label: UITextConstants.permissionMicrophoneLabel,
        primerTitle: UITextConstants.chatVoicePermissionPrimerTitle,
        primerMessage: UITextConstants.chatVoicePermissionPrimerMessage,
        settingsPathMessage: UITextConstants.chatVoicePermissionOpenSettings,
        deniedMessage: UITextConstants.chatVoicePermissionDenied,
      ),
      AppPermissionKind.camera => const AppPermissionCopy(
        label: UITextConstants.permissionCameraLabel,
        primerTitle: UITextConstants.cameraPermissionRequiredTitle,
        primerMessage: UITextConstants.cameraPermissionPrimerMessage,
        settingsPathMessage: UITextConstants.cameraPermissionRequiredRecovery,
        deniedMessage: UITextConstants.cameraPermissionRequired,
      ),
      AppPermissionKind.photos => const AppPermissionCopy(
        label: UITextConstants.permissionPhotosLabel,
        primerTitle: UITextConstants.permissionPhotosPrimerTitle,
        primerMessage: UITextConstants.permissionPhotosPrimerMessage,
        settingsPathMessage: UITextConstants.permissionPhotosOpenSettings,
        deniedMessage: UITextConstants.mediaPickerPermissionDenied,
      ),
      AppPermissionKind.location => const AppPermissionCopy(
        label: UITextConstants.permissionLocationLabel,
        primerTitle: UITextConstants.permissionLocationPrimerTitle,
        primerMessage: UITextConstants.permissionLocationPrimerMessage,
        settingsPathMessage: UITextConstants.permissionLocationOpenSettings,
        deniedMessage: UITextConstants.permissionLocationDenied,
      ),
      AppPermissionKind.contacts => const AppPermissionCopy(
        label: UITextConstants.permissionContactsLabel,
        primerTitle: UITextConstants.permissionContactsPrimerTitle,
        primerMessage: UITextConstants.permissionContactsPrimerMessage,
        settingsPathMessage: UITextConstants.permissionContactsOpenSettings,
        deniedMessage: UITextConstants.permissionContactsDenied,
      ),
      AppPermissionKind.notifications => const AppPermissionCopy(
        label: UITextConstants.permissionNotificationsLabel,
        primerTitle: UITextConstants.permissionNotificationsPrimerTitle,
        primerMessage: UITextConstants.permissionNotificationsPrimerMessage,
        settingsPathMessage:
            UITextConstants.permissionNotificationsOpenSettings,
        deniedMessage: UITextConstants.permissionNotificationsDenied,
      ),
    };
  }

  Future<AppPermissionPhase> phase(AppPermissionKind kind) async {
    final reader = phaseReaders[kind];
    if (reader == null) {
      _registerDefaultAdapters();
    }
    final resolvedReader = phaseReaders[kind];
    if (resolvedReader == null) {
      return AppPermissionPhase.settingsRequired;
    }
    return resolvedReader();
  }

  Future<bool> isGranted(AppPermissionKind kind) async {
    final checker = grantCheckers[kind];
    if (checker != null) {
      return checker();
    }
    final phaseReader = phaseReaders[kind];
    if (phaseReader != null) {
      final currentPhase = await phaseReader();
      return currentPhase == AppPermissionPhase.granted;
    }
    _registerDefaultAdapters();
    final resolvedChecker = grantCheckers[kind];
    if (resolvedChecker == null) {
      return false;
    }
    return resolvedChecker();
  }

  void markSettingsVisitPending(
    AppPermissionKind kind, {
    void Function(bool granted)? onReturn,
  }) {
    final session = _sessionFor(kind);
    session.settingsVisitPending = true;
    session.onSettingsReturn = onReturn;
  }

  Future<bool> openSettings(
    AppPermissionKind kind, {
    void Function(bool granted)? onReturn,
  }) async {
    markSettingsVisitPending(kind, onReturn: onReturn);
    final opened = await settingsOpener();
    if (!opened) {
      final session = _sessionFor(kind);
      session.settingsVisitPending = false;
      session.onSettingsReturn = null;
    }
    return opened;
  }

  Future<AppPermissionEnsureOutcome> ensure(
    BuildContext context,
    AppPermissionKind kind, {
    AppPermissionSurface surface = AppPermissionSurface.page,
    bool showUiOnFailure = true,
    bool? showPrimer,
    bool forceRetry = false,
    void Function(bool granted)? onSettingsReturn,
  }) async {
    ensureLifecycleAttached();
    final session = _sessionFor(kind);
    final effectiveShowPrimer =
        showPrimer ?? surface == AppPermissionSurface.page;
    if (forceRetry) {
      session.suppressSettingsPrompt = false;
    }

    final currentPhase = await phase(kind);
    if (currentPhase == AppPermissionPhase.granted) {
      session.suppressSettingsPrompt = false;
      return AppPermissionEnsureOutcome.granted;
    }
    if (!context.mounted) {
      return switch (currentPhase) {
        AppPermissionPhase.restricted => AppPermissionEnsureOutcome.restricted,
        AppPermissionPhase.settingsRequired =>
          AppPermissionEnsureOutcome.settingsRequired,
        AppPermissionPhase.requestable => AppPermissionEnsureOutcome.denied,
        AppPermissionPhase.granted => AppPermissionEnsureOutcome.granted,
      };
    }
    if (currentPhase == AppPermissionPhase.restricted) {
      if (showUiOnFailure) {
        await _showSoftToast(
          context,
          UITextConstants.permissionRestrictedMessage(copyFor(kind).label),
        );
      }
      return AppPermissionEnsureOutcome.restricted;
    }

    if (currentPhase == AppPermissionPhase.settingsRequired) {
      return _ensureSettingsRequired(
        context,
        kind,
        session: session,
        showUiOnFailure: showUiOnFailure,
        onSettingsReturn: onSettingsReturn,
      );
    }

    if (effectiveShowPrimer && showUiOnFailure) {
      if (!context.mounted) {
        return AppPermissionEnsureOutcome.denied;
      }
      final accepted = await _maybeShowPrimer(context, kind);
      if (!accepted) {
        return AppPermissionEnsureOutcome.denied;
      }
    }

    final requester = requesters[kind];
    final granted = requester != null ? await requester() : false;
    if (granted) {
      session.suppressSettingsPrompt = false;
      return AppPermissionEnsureOutcome.granted;
    }

    final afterPhase = await phase(kind);
    if (afterPhase == AppPermissionPhase.granted) {
      session.suppressSettingsPrompt = false;
      return AppPermissionEnsureOutcome.granted;
    }
    if (!context.mounted) {
      return afterPhase == AppPermissionPhase.requestable
          ? AppPermissionEnsureOutcome.denied
          : AppPermissionEnsureOutcome.settingsRequired;
    }
    if (afterPhase == AppPermissionPhase.requestable) {
      if (showUiOnFailure) {
        await _showSoftToast(context, copyFor(kind).deniedMessage);
      }
      return AppPermissionEnsureOutcome.denied;
    }

    return _ensureSettingsRequired(
      context,
      kind,
      session: session,
      showUiOnFailure: showUiOnFailure,
      onSettingsReturn: onSettingsReturn,
    );
  }

  UiErrorSemantic permissionSemantic(
    AppPermissionKind kind, {
    required bool openSettings,
    bool includeRetry = false,
  }) {
    final copy = copyFor(kind);
    return UiErrorSemantic(
      category: UiErrorCategory.permissionRequired,
      scope: UiErrorScope.dialog,
      title: openSettings
          ? UITextConstants.permissionSettingsGateTitle(copy.label)
          : copy.primerTitle,
      message: openSettings ? copy.settingsPathMessage : copy.deniedMessage,
      primaryAction: UiErrorAction(
        type: openSettings
            ? UiErrorActionType.openSettings
            : (includeRetry
                  ? UiErrorActionType.retry
                  : UiErrorActionType.dismiss),
        label: openSettings
            ? UITextConstants.openSettings
            : (includeRetry
                  ? UITextConstants.permissionRetryAuthorization
                  : UITextConstants.confirm),
      ),
      secondaryAction: openSettings
          ? UiErrorAction(
              type: includeRetry
                  ? UiErrorActionType.retry
                  : UiErrorActionType.dismiss,
              label: includeRetry
                  ? UITextConstants.permissionRetryAuthorization
                  : UITextConstants.cancel,
            )
          : null,
      dismissible: true,
      presentation: UiErrorPresentation.gateCard,
      tone: UiErrorTone.info,
    );
  }

  Future<AppPermissionEnsureOutcome> _ensureSettingsRequired(
    BuildContext context,
    AppPermissionKind kind, {
    required AppPermissionSessionState session,
    required bool showUiOnFailure,
    void Function(bool granted)? onSettingsReturn,
  }) async {
    if (session.suppressSettingsPrompt) {
      if (showUiOnFailure && context.mounted) {
        await _showSoftToast(
          context,
          UITextConstants.permissionStillDeniedMessage(copyFor(kind).label),
        );
      }
      return AppPermissionEnsureOutcome.softDenied;
    }

    if (!showUiOnFailure || !context.mounted) {
      return AppPermissionEnsureOutcome.settingsRequired;
    }

    await AppActionErrorFeedback.show(
      context,
      semantic: permissionSemantic(kind, openSettings: true),
      onAction: (action) async {
        if (action.type == UiErrorActionType.openSettings) {
          markSettingsVisitPending(kind, onReturn: onSettingsReturn);
          await settingsOpener();
        }
      },
    );
    return AppPermissionEnsureOutcome.settingsRequired;
  }

  Future<AppPermissionEnsureOutcome> ensurePageGate(
    BuildContext context,
    AppPermissionKind kind, {
    bool forceRetry = false,
  }) async {
    final outcome = await ensure(
      context,
      kind,
      showUiOnFailure: false,
      showPrimer: false,
      forceRetry: forceRetry,
    );
    if (outcome == AppPermissionEnsureOutcome.granted) {
      return outcome;
    }
    if (!context.mounted) {
      return outcome;
    }
    final session = _sessionFor(kind);
    if (session.suppressSettingsPrompt ||
        outcome == AppPermissionEnsureOutcome.softDenied) {
      await _showSoftToast(
        context,
        UITextConstants.permissionStillDeniedMessage(copyFor(kind).label),
      );
      return AppPermissionEnsureOutcome.softDenied;
    }

    final copy = copyFor(kind);
    await showAppCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(copy.primerTitle),
        content: Text(copy.settingsPathMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text(UITextConstants.cancel),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () {
              Navigator.of(dialogContext).pop();
              unawaited(openSettings(kind));
            },
            child: const Text(UITextConstants.openSettings),
          ),
        ],
      ),
    );
    return AppPermissionEnsureOutcome.settingsRequired;
  }

  Future<void> _handleSettingsReturn() async {
    for (final entry in _sessions.entries) {
      final kind = entry.key;
      final session = entry.value;
      if (!session.settingsVisitPending) {
        continue;
      }
      session.settingsVisitPending = false;
      final callback = session.onSettingsReturn;
      session.onSettingsReturn = null;

      final granted = await isGranted(kind);
      final label = copyFor(kind).label;
      final toastContext = _toastContext;
      if (granted) {
        session.suppressSettingsPrompt = false;
        if (toastContext != null && toastContext.mounted) {
          AppToast.show(
            toastContext,
            UITextConstants.permissionGrantedMessage(label),
          );
        }
        callback?.call(true);
      } else {
        session.suppressSettingsPrompt = true;
        if (toastContext != null && toastContext.mounted) {
          AppToast.show(
            toastContext,
            UITextConstants.permissionStillDeniedMessage(label),
          );
        }
        callback?.call(false);
      }
    }
  }

  AppPermissionSessionState _sessionFor(AppPermissionKind kind) {
    return _sessions.putIfAbsent(kind, AppPermissionSessionState.new);
  }

  Future<bool> _maybeShowPrimer(
    BuildContext context,
    AppPermissionKind kind,
  ) async {
    final checker = primerCheckers[kind];
    if (checker != null && await checker()) {
      return true;
    }
    if (!context.mounted) {
      return false;
    }
    final copy = copyFor(kind);
    final accepted = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(copy.primerTitle),
        content: Text(copy.primerMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(UITextConstants.cancel),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(UITextConstants.permissionPrimerContinue),
          ),
        ],
      ),
    );
    if (accepted != true) {
      return false;
    }
    final marker = primerMarkers[kind];
    if (marker != null) {
      await marker();
    }
    return true;
  }

  Future<void> _showSoftToast(BuildContext context, String message) async {
    if (!context.mounted) {
      return;
    }
    AppToast.show(context, message);
  }

  void _registerDefaultAdapters() {
    _registerPermissionHandlerKind(
      AppPermissionKind.microphone,
      Permission.microphone,
      grantFallback: _microphoneRecordGranted,
    );
    _registerPermissionHandlerKind(AppPermissionKind.camera, Permission.camera);
    _registerPermissionHandlerKind(
      AppPermissionKind.contacts,
      Permission.contacts,
    );
    _registerPermissionHandlerKind(
      AppPermissionKind.notifications,
      Permission.notification,
    );
    _registerPhotosAdapter();
    _registerLocationAdapter();
    _registerPrimerDefaults(AppPermissionKind.microphone);
    _registerPrimerDefaults(AppPermissionKind.camera);
    _registerPrimerDefaults(AppPermissionKind.photos);
    _registerPrimerDefaults(AppPermissionKind.location);
    _registerPrimerDefaults(AppPermissionKind.contacts);
    _registerPrimerDefaults(AppPermissionKind.notifications);
  }

  void _registerPermissionHandlerKind(
    AppPermissionKind kind,
    Permission permission, {
    Future<bool> Function()? grantFallback,
  }) {
    phaseReaders[kind] = () async {
      final status = await permission.status;
      if (status.isGranted) {
        return AppPermissionPhase.granted;
      }
      if (status.isRestricted) {
        return AppPermissionPhase.restricted;
      }
      if (status.isPermanentlyDenied) {
        return AppPermissionPhase.settingsRequired;
      }
      if (grantFallback != null && await grantFallback()) {
        return AppPermissionPhase.granted;
      }
      return AppPermissionPhase.requestable;
    };
    grantCheckers[kind] = () async {
      if ((await permission.status).isGranted) {
        return true;
      }
      return grantFallback != null ? grantFallback() : false;
    };
    requesters[kind] = () async {
      final requested = await permission.request();
      return requested.isGranted;
    };
  }

  void _registerPhotosAdapter() {
    phaseReaders[AppPermissionKind.photos] = () async {
      final state = await PhotoManager.getPermissionState(
        requestOption: const PermissionRequestOption(),
      );
      if (state.isAuth || state.hasAccess) {
        return AppPermissionPhase.granted;
      }
      if (state == PermissionState.denied ||
          state == PermissionState.notDetermined) {
        return AppPermissionPhase.requestable;
      }
      return AppPermissionPhase.settingsRequired;
    };
    grantCheckers[AppPermissionKind.photos] = () async {
      final state = await PhotoManager.getPermissionState(
        requestOption: const PermissionRequestOption(),
      );
      return state.isAuth || state.hasAccess;
    };
    requesters[AppPermissionKind.photos] = () async {
      final state = await PhotoManager.requestPermissionExtend();
      return state.isAuth || state.hasAccess;
    };
  }

  void _registerLocationAdapter() {
    phaseReaders[AppPermissionKind.location] = () async {
      await StartupDeferredPlugins.ensureLocationPlugins();
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        return AppPermissionPhase.settingsRequired;
      }
      final perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.always ||
          perm == LocationPermission.whileInUse) {
        return AppPermissionPhase.granted;
      }
      if (perm == LocationPermission.deniedForever) {
        return AppPermissionPhase.settingsRequired;
      }
      return AppPermissionPhase.requestable;
    };
    grantCheckers[AppPermissionKind.location] = () async {
      await StartupDeferredPlugins.ensureLocationPlugins();
      final perm = await Geolocator.checkPermission();
      return perm == LocationPermission.always ||
          perm == LocationPermission.whileInUse;
    };
    requesters[AppPermissionKind.location] = () async {
      await StartupDeferredPlugins.ensureLocationPlugins();
      if (!await Geolocator.isLocationServiceEnabled()) {
        return false;
      }
      final perm = await Geolocator.requestPermission();
      return perm == LocationPermission.always ||
          perm == LocationPermission.whileInUse;
    };
  }

  void _registerPrimerDefaults(AppPermissionKind kind) {
    final key = _primerPrefsKeys[kind]!;
    primerCheckers[kind] = () async {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(key) ?? false;
    };
    primerMarkers[kind] = () async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(key, true);
    };
  }

  static Future<bool> _microphoneRecordGranted() async {
    final recorder = AudioRecorder();
    try {
      return await recorder.hasPermission(request: false);
    } finally {
      await recorder.dispose();
    }
  }
}
