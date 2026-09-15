import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/presentation/post_collection_editor.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/l10n/copy/post_collection_text_constants.dart';
import 'package:quwoquan_app/runtime/di/post_collection_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';

/// 独立合集读取页；成员导航由组合根注入，不依赖 viewer 私有实现。
class PostCollectionPage extends ConsumerStatefulWidget {
  const PostCollectionPage({
    super.key,
    required this.collectionId,
    required this.openPost,
  });
  final String collectionId;
  final void Function(String postId) openPost;
  @override
  ConsumerState<PostCollectionPage> createState() => _PostCollectionPageState();
}

class _PostCollectionPageState extends ConsumerState<PostCollectionPage> {
  contracts.PostCollectionPage? _page;
  final _members = <contracts.PostCollectionMemberSummary>[];
  Object? _error;
  bool _loading = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool more = false}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final target = more ? _members.length + 20 : 20;
      final refreshed = <contracts.PostCollectionMemberSummary>[];
      String? cursor;
      contracts.PostCollectionPage page;
      do {
        page = await ref
            .read(postCollectionPortProvider)
            .get(
              contracts.GetPostCollectionQuery(
                collectionId: widget.collectionId,
                cursor: cursor,
                limit: 20,
              ),
            );
        refreshed.addAll(page.members);
        cursor = page.nextCursor;
      } while (cursor != null && refreshed.length < target);
      if (!mounted) return;
      setState(() {
        _members
          ..clear()
          ..addAll(refreshed);
        _page = page;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _edit() async {
    final page = _page;
    if (page == null || !page.canManage || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final port = ref.read(postCollectionPortProvider);
      final view = await port.management(
        contracts.GetPostCollectionManagementQuery(
          collectionId: page.collectionId,
        ),
      );
      if (!mounted) return;
      final saved = await Navigator.of(context).push<bool>(
        CupertinoPageRoute(
          builder: (_) => PostCollectionEditor(
            port: port,
            view: view,
            personaId: page.ownerPersonaId,
          ),
        ),
      );
      if (mounted) {
        setState(() => _loading = false);
        if (saved == true) await _load();
      }
    } catch (error) {
      if (mounted)
        setState(() {
          _error = error;
          _loading = false;
        });
    }
  }

  Future<void> _delete() async {
    final page = _page;
    if (page == null || !page.canManage || _loading) return;
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text(PostCollectionText.delete),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.pop(context, false),
            child: const Text(PostCollectionText.cancelled),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.pop(context, true),
            child: const Text(PostCollectionText.delete),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref
          .read(postCollectionPortProvider)
          .delete(
            contracts.DeletePostCollectionCommand(
              collectionId: page.collectionId,
              expectedVersion: page.version,
            ),
          );
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error;
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final error = _error;
    final page = _page;
    return AppScaffold(
      navigationBar: CupertinoNavigationBar(
        middle: Text(page?.name ?? PostCollectionText.title),
      ),
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.all(AppSpacing.md),
          children: [
            if (_loading) const CupertinoActivityIndicator(),
            if (error != null) ...[
              Text(
                UiErrorSemanticResolver.resolve(
                  context,
                  error: error,
                  category: UiErrorCategory.pageLoad,
                  scope: UiErrorScope.page,
                ).message,
              ),
              CupertinoButton(
                onPressed: _loading ? null : () => _load(),
                child: const Text(PostCollectionText.refresh),
              ),
            ] else if (page != null) ...[
              Text(PostCollectionText.count(page.visibleCount)),
              if (page.canManage) ...[
                CupertinoButton(
                  onPressed: _loading ? null : _edit,
                  child: const Text(PostCollectionText.edit),
                ),
                CupertinoButton(
                  onPressed: _loading ? null : _delete,
                  child: const Text(PostCollectionText.delete),
                ),
              ],
              if (_members.isEmpty) const Text(PostCollectionText.empty),
              for (final member in _members)
                CupertinoButton(
                  onPressed: () => widget.openPost(member.postId),
                  child: Text(member.title),
                ),
              if (page.nextCursor != null)
                CupertinoButton(
                  onPressed: _loading ? null : () => _load(more: true),
                  child: const Text(PostCollectionText.loadMore),
                ),
              CupertinoButton(
                onPressed: _loading ? null : () => _load(),
                child: const Text(PostCollectionText.refresh),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
