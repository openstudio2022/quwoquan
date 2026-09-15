import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart' as wire;
import 'package:quwoquan_app/service/content_service/content/post_collection/application/post_collection_port.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/l10n/copy/post_collection_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';

/// 完整 owner 编排输入与作者作品选择，内部标识只在 typed 命令中流转。
class PostCollectionEditor extends StatefulWidget {
  const PostCollectionEditor({
    super.key,
    required this.port,
    required this.view,
    required this.personaId,
  });
  final PostCollectionPort port;
  final wire.PostCollectionManagementView view;
  final String personaId;
  @override
  State<PostCollectionEditor> createState() => _PostCollectionEditorState();
}

class _PostCollectionEditorState extends State<PostCollectionEditor> {
  late final _name = TextEditingController(text: widget.view.name);
  late final _members = [...widget.view.members];
  late var _visibility = widget.view.visibility;
  late String? _cover = widget.view.coverAssetId;
  final _posts = <wire.ContentPostProjection>[];
  String? _cursor;
  Object? _error;
  bool _busy = false;
  bool _more = true;
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.port.authorPosts(
        wire.ContentAuthorPostsQuery(
          personaId: widget.personaId,
          cursor: _cursor,
          limit: 20,
        ),
      );
      if (!mounted) return;
      setState(() {
        _posts.addAll(
          result.items.where(
            (p) =>
                p.contentType == 'video' ||
                p.contentType == 'image' ||
                p.contentType == 'article',
          ),
        );
        _cursor = result.nextCursor;
        _more = result.hasMore;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.port.save(
        wire.SavePostCollectionCommand(
          collectionId: widget.view.collectionId,
          expectedVersion: widget.view.version,
          name: _name.text.trim(),
          coverAssetId: _cover,
          visibility: _visibility,
          postIds: _members.map((m) => m.postId).toList(),
        ),
      );
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted)
        setState(() {
          _error = e;
          _busy = false;
        });
    }
  }

  String? _imageAsset(wire.ContentPostProjection post) {
    for (final media in post.mediaItems ?? <wire.PostMediaItem>[]) {
      if (media.kind == 'image' && media.mediaAssetId != null)
        return media.mediaAssetId;
    }
    return post.contentType == 'image' ? post.mediaAssetId : null;
  }

  @override
  Widget build(BuildContext context) => AppScaffold(
    navigationBar: const CupertinoNavigationBar(
      middle: Text(PostCollectionText.edit),
    ),
    child: SafeArea(
      child: ListView(
        padding: EdgeInsets.all(AppSpacing.md),
        children: [
          CupertinoTextField(
            controller: _name,
            placeholder: PostCollectionText.name,
          ),
          Row(
            children: [
              const Expanded(child: Text(PostCollectionText.private)),
              CupertinoSwitch(
                value: _visibility == wire.PostCollectionVisibility.private,
                onChanged: _busy
                    ? null
                    : (value) => setState(
                        () => _visibility = value
                            ? wire.PostCollectionVisibility.private
                            : wire.PostCollectionVisibility.public,
                      ),
              ),
            ],
          ),
          if (_cover != null)
            CupertinoButton(
              onPressed: _busy ? null : () => setState(() => _cover = null),
              child: const Text(PostCollectionText.clearCover),
            ),
          const Text(PostCollectionText.members),
          for (var i = 0; i < _members.length; i++)
            Row(
              children: [
                Expanded(
                  child: Text(
                    _members[i].title ?? PostCollectionText.unavailableMember,
                  ),
                ),
                CupertinoButton(
                  onPressed: _busy || i == 0
                      ? null
                      : () => setState(() {
                          final item = _members.removeAt(i);
                          _members.insert(i - 1, item);
                        }),
                  child: const Text(PostCollectionText.moveUp),
                ),
                CupertinoButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() => _members.removeAt(i)),
                  child: const Text(PostCollectionText.remove),
                ),
              ],
            ),
          const Text(PostCollectionText.choosePosts),
          for (final post in _posts)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CupertinoButton(
                  onPressed:
                      _busy || _members.any((m) => m.postId == post.postId)
                      ? null
                      : () => setState(
                          () => _members.add(
                            wire.PostCollectionManagedMember(
                              postId: post.postId,
                              readable: true,
                              title:
                                  post.title ?? PostCollectionText.unnamedPost,
                            ),
                          ),
                        ),
                  child: Text(post.title ?? PostCollectionText.unnamedPost),
                ),
                if (_imageAsset(post) != null)
                  CupertinoButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() => _cover = _imageAsset(post)),
                    child: Text(
                      _cover == _imageAsset(post)
                          ? PostCollectionText.selectedCover
                          : PostCollectionText.cover,
                    ),
                  ),
              ],
            ),
          if (_error != null)
            Text(
              UiErrorSemanticResolver.resolve(
                context,
                error: _error!,
                category: UiErrorCategory.submit,
                scope: UiErrorScope.form,
              ).message,
            ),
          if (_busy) const CupertinoActivityIndicator(),
          if (_more)
            CupertinoButton(
              onPressed: _busy ? null : _load,
              child: const Text(PostCollectionText.loadMore),
            ),
          CupertinoButton(
            onPressed: _busy ? null : _save,
            child: const Text(PostCollectionText.save),
          ),
        ],
      ),
    ),
  );
}
