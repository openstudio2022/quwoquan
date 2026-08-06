import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/shell/legal/legal_document_remote.dart';
import 'package:webview_flutter/webview_flutter.dart';

typedef LegalDocumentAvailabilityProbe = Future<bool> Function(Uri uri);
typedef LegalDocumentHtmlLoader = Future<String> Function(Uri uri);
typedef LegalDocumentWebViewBuilder =
    Widget Function(BuildContext context, WebViewController controller);

class LegalDocumentPage extends StatefulWidget {
  const LegalDocumentPage({
    super.key,
    required this.title,
    required this.url,
    required this.journeyEventTracker,
    this.availabilityProbe = defaultLegalDocumentAvailabilityProbe,
    this.htmlLoader = defaultLegalDocumentHtmlLoader,
    this.webViewBuilder = _defaultLegalDocumentWebViewBuilder,
  });

  final String title;
  final String url;
  final JourneyEventTracker journeyEventTracker;
  final LegalDocumentAvailabilityProbe availabilityProbe;
  final LegalDocumentHtmlLoader htmlLoader;
  final LegalDocumentWebViewBuilder webViewBuilder;

  @override
  State<LegalDocumentPage> createState() => _LegalDocumentPageState();
}

class _LegalDocumentPageState extends State<LegalDocumentPage> {
  WebViewController? _controller;
  bool _isLoading = true;
  bool _hasError = false;
  int _loadGeneration = 0;
  int? _lastTrackedFailureGeneration;

  @override
  void initState() {
    super.initState();
    unawaited(_loadDocument());
  }

  @override
  void didUpdateWidget(covariant LegalDocumentPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url ||
        oldWidget.availabilityProbe != widget.availabilityProbe) {
      unawaited(_loadDocument());
    }
  }

  WebViewController _ensureController() {
    final existing = _controller;
    if (existing != null) {
      return existing;
    }
    final next = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.disabled)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) {
            if (!mounted) return;
            setState(() {
              _isLoading = true;
              _hasError = false;
            });
          },
          onPageFinished: (_) {
            if (!mounted) return;
            setState(() => _isLoading = false);
          },
          onWebResourceError: (_) {
            _markLoadFailed(reason: 'web_resource_error');
          },
          onHttpError: (error) {
            _markLoadFailed(
              reason: 'http_error',
              statusCode: error.response?.statusCode,
            );
          },
        ),
      );
    _controller = next;
    return next;
  }

  Future<void> _loadDocument() async {
    final generation = ++_loadGeneration;
    if (mounted) {
      setState(() {
        _isLoading = true;
        _hasError = false;
      });
    }
    final uri = Uri.tryParse(widget.url);
    if (uri == null || !_isHttpUrl(uri)) {
      _markLoadFailed(generation: generation, reason: 'invalid_url');
      return;
    }
    bool available;
    try {
      available = await widget.availabilityProbe(uri);
    } catch (_) {
      _markLoadFailed(generation: generation, reason: 'preflight_exception');
      return;
    }
    if (!mounted || generation != _loadGeneration) {
      return;
    }
    if (!available) {
      _markLoadFailed(generation: generation, reason: 'preflight_failed');
      return;
    }
    final controller = _ensureController();
    if (mounted && generation == _loadGeneration) {
      setState(() {});
    }
    try {
      final html = await widget.htmlLoader(uri);
      if (!mounted || generation != _loadGeneration) {
        return;
      }
      await controller.loadHtmlString(html, baseUrl: uri.toString());
    } catch (_) {
      _markLoadFailed(generation: generation, reason: 'load_request_failed');
    }
  }

  void _markLoadFailed({
    int? generation,
    required String reason,
    int? statusCode,
  }) {
    if (!mounted) return;
    final effectiveGeneration = generation ?? _loadGeneration;
    if (effectiveGeneration != _loadGeneration) return;
    _trackLoadFailureOnce(
      effectiveGeneration,
      reason: reason,
      statusCode: statusCode,
    );
    setState(() {
      _isLoading = false;
      _hasError = true;
    });
  }

  Future<void> _retry() async {
    await _loadDocument();
  }

  void _goBack() {
    if (context.canPop()) {
      context.pop();
    }
  }

  void _trackLoadFailureOnce(
    int generation, {
    required String reason,
    int? statusCode,
  }) {
    if (_lastTrackedFailureGeneration == generation) {
      return;
    }
    _lastTrackedFailureGeneration = generation;
    final slug = _legalDocumentSlug(widget.url);
    final payload = <String, Object?>{
      'document': slug,
      'runtimeEnv': CloudRuntimeConfig.appRuntimeEnv,
      'failureReason': reason,
    };
    if (statusCode != null) {
      payload['httpStatus'] = statusCode;
    }
    unawaited(
      widget.journeyEventTracker.trackAction(
        journey: 'legal_document',
        action: 'load_failed',
        pageName: 'legal_document_page',
        targetType: 'legal_document',
        targetKey: slug,
        payload: payload,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return AppScaffold(
      backgroundColor: AppColors.iosSystemBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: _goBack,
        ),
        middle: Text(
          widget.title,
          style: AppNavigationSemanticConstants.barTitleTextStyle(false),
        ),
      ),
      body: SafeArea(
        child: Stack(
          children: <Widget>[
            if (_hasError)
              AppPageErrorState(
                semantic: AppUserRecoveryContract.semanticFor(
                  group: AppUserRecoveryGroup.reloadLater,
                  category: UiErrorCategory.pageLoad,
                  scope: UiErrorScope.page,
                ),
                onRecovery: (action) async {
                  if (action.type == UiErrorActionType.retry ||
                      action.type == UiErrorActionType.resubmit) {
                    await _retry();
                    return _hasError
                        ? UiRecoveryOutcome.stillBlocked
                        : UiRecoveryOutcome.recovered;
                  }
                  return UiRecoveryOutcome.cancelled;
                },
              )
            else if (controller == null)
              const SizedBox.shrink()
            else
              widget.webViewBuilder(context, controller),
            if (_isLoading) AppRequestFeedback.section(),
          ],
        ),
      ),
    );
  }
}

bool _isHttpUrl(Uri uri) {
  return uri.scheme == 'http' || uri.scheme == 'https';
}

Widget _defaultLegalDocumentWebViewBuilder(
  BuildContext context,
  WebViewController controller,
) {
  return WebViewWidget(controller: controller);
}

String _legalDocumentSlug(String url) {
  final uri = Uri.tryParse(url);
  final segments = uri?.pathSegments ?? const <String>[];
  for (final segment in segments.reversed) {
    final trimmed = segment.trim();
    if (trimmed.isEmpty || trimmed == 'legal') {
      continue;
    }
    return trimmed.endsWith('.html')
        ? trimmed.substring(0, trimmed.length - '.html'.length)
        : trimmed;
  }
  return 'unknown';
}
