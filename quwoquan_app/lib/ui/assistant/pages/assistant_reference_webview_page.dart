import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

// settings-canonical-exception: WebView 全屏内容宿主 CR-20260329-003

class AssistantReferenceWebViewPage extends StatefulWidget {
  const AssistantReferenceWebViewPage({
    super.key,
    required this.initialUrl,
    this.title = '',
    this.source = '',
  });

  final String initialUrl;
  final String title;
  final String source;

  @override
  State<AssistantReferenceWebViewPage> createState() =>
      _AssistantReferenceWebViewPageState();
}

class _AssistantReferenceWebViewPageState
    extends State<AssistantReferenceWebViewPage> {
  late final WebViewController _controller;
  late final Uri _uri;
  bool _isLoading = true;
  bool _hasError = false;
  bool? _webViewSurfaceIsDark;
  int _loadingProgress = 6;
  Timer? _hideProgressTimer;

  @override
  void initState() {
    super.initState();
    _uri = Uri.parse(widget.initialUrl);
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (progress) {
            if (!mounted) return;
            _hideProgressTimer?.cancel();
            setState(() {
              _loadingProgress = progress.clamp(0, 100);
              _isLoading = _loadingProgress < 100;
            });
            if (_loadingProgress >= 100) {
              _scheduleHideProgress();
            }
          },
          onPageStarted: (_) {
            if (!mounted) return;
            _hideProgressTimer?.cancel();
            setState(() {
              _isLoading = true;
              _hasError = false;
              _loadingProgress = 6;
            });
          },
          onPageFinished: (_) {
            if (!mounted) return;
            _hideProgressTimer?.cancel();
            setState(() {
              _hasError = false;
              _loadingProgress = 100;
            });
            _scheduleHideProgress();
          },
          onWebResourceError: (_) {
            if (!mounted) return;
            _hideProgressTimer?.cancel();
            setState(() {
              _isLoading = false;
              _hasError = true;
              _loadingProgress = 0;
            });
          },
        ),
      )
      ..loadRequest(_uri);
  }

  @override
  void dispose() {
    _hideProgressTimer?.cancel();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    if (_webViewSurfaceIsDark != isDark) {
      _webViewSurfaceIsDark = isDark;
      _controller.setBackgroundColor(
        AppColorsFunctional.getColor(
          isDark,
          ColorType.webViewPlaceholderBackground,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final title = widget.title.trim().isNotEmpty
        ? widget.title.trim()
        : widget.source.trim().isNotEmpty
        ? widget.source.trim()
        : UITextConstants.assistantReferenceSectionTitle;
    return AppScaffold(
      backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
      navigationBar: AppNavigationBar(
        middle: Text(
          title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          children: [
            SizedBox(
              height: AppSpacing.xs,
              child: AnimatedOpacity(
                opacity: _isLoading ? 1 : 0,
                duration: const Duration(milliseconds: 120),
                child: LinearProgressIndicator(
                  value: _loadingProgress / 100,
                  minHeight: AppSpacing.xs,
                  backgroundColor: AppColors.transparent,
                  color: AppColors.primaryColor,
                ),
              ),
            ),
            Expanded(
              child: _hasError
                  ? _ReferenceLoadError(onRetry: _reload, host: _uri.host)
                  : WebViewWidget(controller: _controller),
            ),
          ],
        ),
      ),
    );
  }

  void _reload() {
    _hideProgressTimer?.cancel();
    setState(() {
      _isLoading = true;
      _hasError = false;
      _loadingProgress = 6;
    });
    _controller.loadRequest(_uri);
  }

  void _scheduleHideProgress() {
    _hideProgressTimer = Timer(const Duration(milliseconds: 900), () {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });
    });
  }
}

class _ReferenceLoadError extends StatelessWidget {
  const _ReferenceLoadError({required this.onRetry, required this.host});

  final VoidCallback onRetry;
  final String host;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final muted = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              CupertinoIcons.exclamationmark_triangle,
              size: AppSpacing.iconLarge + AppSpacing.sm,
              color: muted.withValues(alpha: 0.85),
            ),
            SizedBox(height: AppSpacing.sm),
            Text(
              UITextConstants.loadFailed,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: FontWeight.w600,
                color: fg,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              host.trim().isNotEmpty
                  ? host.trim()
                  : UITextConstants.assistantReferenceSectionTitle,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: AppTypography.sm, color: muted),
            ),
            SizedBox(height: AppSpacing.md),
            CupertinoButton.filled(
              onPressed: onRetry,
              child: Text(UITextConstants.retry),
            ),
          ],
        ),
      ),
    );
  }
}
