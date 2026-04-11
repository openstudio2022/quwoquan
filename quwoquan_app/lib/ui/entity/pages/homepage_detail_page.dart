import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_detail_shell.dart';

class HomepageDetailPage extends ConsumerStatefulWidget {
  const HomepageDetailPage({
    super.key,
    required this.homepageId,
    this.selectionMode = false,
    this.initialSummary,
  });

  final String homepageId;
  final bool selectionMode;
  final HomepageSummary? initialSummary;

  @override
  ConsumerState<HomepageDetailPage> createState() => _HomepageDetailPageState();
}

class _HomepageDetailPageState extends ConsumerState<HomepageDetailPage> {
  bool _isLoading = true;
  String? _errorText;
  HomepageDetail? _detail;
  HomepageShellData? _shell;
  String? _viewerOwnerUserId;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  Widget build(BuildContext context) {
    return HomepageDetailShell(
      selectionMode: widget.selectionMode,
      initialSummary: widget.initialSummary,
      isLoading: _isLoading,
      errorText: _errorText,
      detail: _detail,
      shell: _shell,
      viewerOwnerUserId: _viewerOwnerUserId,
      onBack: () => context.pop(),
      onClaim: _openClaim,
      onMaintain: _openMaintenance,
      onReport: _openStatusReport,
      onCreateContent: _openCreateContent,
      onAttach: (reference) => context.pop(reference),
    );
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorText = null;
    });
    try {
      final repository = ref.read(homepageRepositoryProvider);
      late HomepageDetail loadedDetail;
      late HomepageShellData loadedShell;
      await Future.wait<void>([
        repository.getHomepageDetail(widget.homepageId).then((d) {
          loadedDetail = d;
        }),
        repository.getHomepageShell(widget.homepageId).then((s) {
          loadedShell = s;
        }),
      ]);
      ActivePersonaContextViewData? activeContext;
      try {
        activeContext = await ref.read(activePersonaContextProvider.future);
      } catch (_) {
        activeContext = null;
      }
      if (!mounted) {
        return;
      }
      final ownerId = activeContext?.ownerUserId.trim() ?? '';
      setState(() {
        _detail = loadedDetail;
        _shell = loadedShell;
        _viewerOwnerUserId = ownerId.isEmpty ? null : ownerId;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorText = '主页详情暂时不可用，请稍后重试';
        _isLoading = false;
      });
    }
  }

  Future<void> _openClaim() async {
    final changed = await context.push<bool>(
      AppRoutePaths.homepageClaim(id: widget.homepageId),
    );
    if (changed == true && mounted) {
      await _load();
    }
  }

  Future<void> _openMaintenance() async {
    final changed = await context.push<bool>(
      AppRoutePaths.homepageMaintenance(id: widget.homepageId),
    );
    if (changed == true && mounted) {
      await _load();
    }
  }

  Future<void> _openStatusReport() async {
    final changed = await context.push<bool>(
      AppRoutePaths.homepageStatusReport(id: widget.homepageId),
    );
    if (changed == true && mounted) {
      await _load();
    }
  }

  void _openCreateContent(HomepageCanonicalReference reference) {
    context.push(AppRoutePaths.create(), extra: reference);
  }
}
