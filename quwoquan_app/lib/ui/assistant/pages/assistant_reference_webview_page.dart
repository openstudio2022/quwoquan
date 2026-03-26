import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

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

  @override
  void initState() {
    super.initState();
    _uri = Uri.parse(widget.initialUrl);
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.white)
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
            setState(() {
              _isLoading = false;
              _hasError = false;
            });
          },
          onWebResourceError: (_) {
            if (!mounted) return;
            setState(() {
              _isLoading = false;
              _hasError = true;
            });
          },
        ),
      )
      ..loadRequest(_uri);
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.source.trim().isNotEmpty
        ? widget.source.trim()
        : widget.title.trim().isNotEmpty
        ? widget.title.trim()
        : UITextConstants.assistantReferenceSectionTitle;
    return AppScaffold(
      backgroundColor: SettingsSemanticConstants.pageBackground(false),
      navigationBar: AppNavigationBar(
        middle: Text(
          title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.semiBold,
            color: SettingsSemanticConstants.labelColor(false),
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: Icon(
            CupertinoIcons.back,
            color: SettingsSemanticConstants.labelColor(false),
          ),
        ),
        trailing: _isLoading
            ? const Padding(
                padding: EdgeInsetsDirectional.only(end: 4),
                child: CupertinoActivityIndicator(),
              )
            : null,
      ),
      child: SafeArea(
        top: false,
        child: Column(
          children: [
            Container(
              width: double.infinity,
              margin: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.sm,
                AppSpacing.containerMd,
                AppSpacing.sm,
              ),
              padding: EdgeInsets.all(AppSpacing.containerSm),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (widget.title.trim().isNotEmpty) ...[
                    Text(
                      widget.title.trim(),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w600,
                        color: Colors.black.withValues(alpha: 0.86),
                        height: AppTypography.bodyLineHeight,
                      ),
                    ),
                    SizedBox(height: AppSpacing.xs),
                  ],
                  Text(
                    widget.initialUrl,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: Colors.black.withValues(alpha: 0.52),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Container(
                margin: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  0,
                  AppSpacing.containerMd,
                  AppSpacing.containerMd,
                ),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                  border: Border.all(
                    color: Colors.black.withValues(alpha: 0.06),
                  ),
                ),
                clipBehavior: Clip.antiAlias,
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: _hasError
                          ? _ReferenceLoadError(
                              onRetry: _reload,
                              host: _uri.host,
                            )
                          : WebViewWidget(controller: _controller),
                    ),
                    if (_isLoading)
                      Positioned(
                        top: 0,
                        left: 0,
                        right: 0,
                        child: LinearProgressIndicator(
                          minHeight: 2,
                          backgroundColor: Colors.transparent,
                          color: AppColors.primaryColor,
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _reload() {
    setState(() {
      _isLoading = true;
      _hasError = false;
    });
    _controller.loadRequest(_uri);
  }
}

class _ReferenceLoadError extends StatelessWidget {
  const _ReferenceLoadError({required this.onRetry, required this.host});

  final VoidCallback onRetry;
  final String host;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              CupertinoIcons.exclamationmark_triangle,
              size: AppSpacing.iconLarge + AppSpacing.sm,
              color: Colors.black.withValues(alpha: 0.3),
            ),
            SizedBox(height: AppSpacing.sm),
            Text(
              UITextConstants.loadFailed,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: FontWeight.w600,
                color: Colors.black.withValues(alpha: 0.82),
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              host.trim().isNotEmpty
                  ? host.trim()
                  : UITextConstants.assistantReferenceSectionTitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: Colors.black.withValues(alpha: 0.56),
              ),
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
