import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:webview_flutter/webview_flutter.dart';

class LegalDocumentPage extends StatefulWidget {
  const LegalDocumentPage({super.key, required this.title, required this.url});

  final String title;
  final String url;

  @override
  State<LegalDocumentPage> createState() => _LegalDocumentPageState();
}

class _LegalDocumentPageState extends State<LegalDocumentPage> {
  late final WebViewController _controller;
  bool _isLoading = true;
  bool _hasError = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
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
            if (!mounted) return;
            setState(() {
              _isLoading = false;
              _hasError = true;
            });
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      backgroundColor: AppColors.iosSystemBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            }
          },
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
              Center(
                child: CupertinoButton(
                  onPressed: () =>
                      _controller.loadRequest(Uri.parse(widget.url)),
                  child: const Text(UITextConstants.legalLoadFailed),
                ),
              )
            else
              WebViewWidget(controller: _controller),
            if (_isLoading) const Center(child: CupertinoActivityIndicator()),
          ],
        ),
      ),
    );
  }
}
