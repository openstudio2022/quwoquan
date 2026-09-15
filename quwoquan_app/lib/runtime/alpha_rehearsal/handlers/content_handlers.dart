import 'dart:async';
import 'dart:convert';

import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/alpha_post_intersection_projector.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';

/// Alpha rehearsal 对 content canonical operations 的能力清单。
///
/// 只有这里列出的 operation 才拥有本地语义；上传需要真实字节接收端，明确不支持。
const Set<String> alphaContentSupportedOperations = <String>{
  'content.comment.BindMediaAssetsToComment',
  'content.comment.CreateComment',
  'content.comment.DeleteComment',
  'content.comment.ListCommentReplies',
  'content.comment.ListComments',
  'content.comment.ListCommentsByAuthor',
  'content.comment.ListCommentsForPostAuthor',
  'content.comment.PinComment',
  'content.comment.UnpinComment',
  'content.content_behavior_fact.ReportBehaviors',
  'content.content_reaction.GetContentReactionState',
  'content.content_reaction.LikePost',
  'content.content_reaction.ReactToComment',
  'content.content_reaction.UnlikePost',
  'content.media_asset.GetMediaAsset',
  'content.outbound_share_fact.AppendOutboundShareFact',
  'content.post.DeletePost',
  'content.post.GetFeed',
  'content.post.GetMyFootprint',
  'content.post.GetPost',
  'content.post.ListUserPosts',
  'content.post_collection.DeletePostCollection',
  'content.post_collection.GetPostCollection',
  'content.post_collection.GetPostCollectionManagement',
  'content.post_collection.SavePostCollection',
  'content.profile_interaction_activity_view.ListProfileInteractionActivitiesReceived',
  'content.profile_interaction_activity_view.ListProfileInteractionActivitiesSent',
  'content.profile_interaction_read_fact.AppendProfileInteractionReadFact',
  'content.report.CreateReport',
  'content.report.ListMyReports',
};

const Set<String> alphaContentUnsupportedOperations = <String>{
  // Bundle 没有这些派生读模型或发布 admission 输入，不能伪造成功。
  'content.post.GetAppConfig',
  'content.post.GetAuthorImpact',
  'content.post.GetEntityWishlistState',
  'content.post.GetGatheringSocialProof',
  'content.post.ListAuthorImpactEvidence',
  'content.post.ListPostsByGathering',
  'content.post.SubmitPostPublication',
  'content.media_asset.DiscardMediaAsset',
  'content.media_asset.SelectAutoVideoCover',
  'content.media_asset.SelectManualVideoCover',
  'content.media_upload_session.AbortMediaUpload',
  'content.media_upload_session.CompleteMediaUpload',
  'content.media_upload_session.GetMediaUploadSession',
  'content.media_upload_session.InitMediaUpload',
};

typedef PostExistenceResolver = FutureOr<bool> Function(String postId);

Future<bool> bundledPostExists(String postId) async {
  final bundle = await OfflineContentBundle.load();
  return bundle.rows('posts').any((row) {
    final detail = row['detail'];
    return detail is Map && detail['postId'] == postId;
  });
}

final class ContentRehearsalHandler implements RehearsalObjectHandler {
  const ContentRehearsalHandler({this.postExists});

  final PostExistenceResolver? postExists;

  @override
  Stream<Object?>? stream(RehearsalInvocation invocation) => null;

  @override
  Future<Object?> handle(RehearsalInvocation invocation) async {
    final id = invocation.operation.canonicalOperationId;
    if (alphaContentUnsupportedOperations.contains(id)) rehearsalUnsupported();
    return switch (id) {
      'content.content_reaction.LikePost' => _like(invocation, liked: true),
      'content.content_reaction.UnlikePost' => _like(invocation, liked: false),
      'content.content_reaction.GetContentReactionState' => _reactionState(
        invocation,
      ),
      'content.content_reaction.ReactToComment' => _reactComment(invocation),
      'content.comment.CreateComment' => _createComment(invocation),
      'content.comment.DeleteComment' => _deleteComment(invocation),
      'content.comment.BindMediaAssetsToComment' => _bindCommentMedia(
        invocation,
      ),
      'content.comment.PinComment' => _pinComment(invocation, pinned: true),
      'content.comment.UnpinComment' => _pinComment(invocation, pinned: false),
      'content.comment.ListComments' ||
      'content.comment.ListCommentReplies' ||
      'content.comment.ListCommentsByAuthor' ||
      'content.comment.ListCommentsForPostAuthor' => _listComments(invocation),
      'content.content_behavior_fact.ReportBehaviors' => _reportBehaviors(
        invocation,
      ),
      'content.media_asset.GetMediaAsset' => _getMedia(invocation),
      'content.outbound_share_fact.AppendOutboundShareFact' => _appendShare(
        invocation,
      ),
      'content.post.GetPost' => _getPost(invocation),
      'content.post.GetFeed' => _getFeed(invocation),
      'content.post.GetMyFootprint' => _footprint(invocation),
      'content.post.ListUserPosts' => _listUserPosts(invocation),
      'content.post.DeletePost' => _deletePost(invocation),
      'content.post_collection.SavePostCollection' => _saveCollection(
        invocation,
      ),
      'content.post_collection.DeletePostCollection' => _deleteCollection(
        invocation,
      ),
      'content.post_collection.GetPostCollection' => _getCollection(
        invocation,
        management: false,
      ),
      'content.post_collection.GetPostCollectionManagement' => _getCollection(
        invocation,
        management: true,
      ),
      'content.profile_interaction_activity_view.ListProfileInteractionActivitiesReceived' =>
        _listInteractions(invocation, received: true),
      'content.profile_interaction_activity_view.ListProfileInteractionActivitiesSent' =>
        _listInteractions(invocation, received: false),
      'content.profile_interaction_read_fact.AppendProfileInteractionReadFact' =>
        _readInteraction(invocation),
      'content.report.CreateReport' => _createReport(invocation),
      'content.report.ListMyReports' => _listReports(invocation),
      _ => rehearsalUnsupported(),
    };
  }

  Map<String, Map<String, Object?>> _table(
    RehearsalInvocation i,
    String name,
  ) =>
      i.store.records.putIfAbsent(name, () => <String, Map<String, Object?>>{});

  String _actor(RehearsalInvocation i) => i.actorId.isNotEmpty
      ? i.actorId
      : 'device:${i.context.actor.deviceActorId ?? 'guest'}';

  Future<List<Map<String, Object?>>> _bundlePosts(RehearsalInvocation i) async {
    final bundle = await OfflineContentBundle.load();
    final deleted = _table(i, 'content.posts');
    return bundle
        .rows('posts')
        .map((row) => Map<String, Object?>.from(row['projection'] as Map))
        .where((post) => deleted['${post['postId']}']?['status'] != 'deleted')
        .toList(growable: false);
  }

  Future<Object?> _like(RehearsalInvocation i, {required bool liked}) =>
      i.store.commit(() async {
        final postId = i.path('postId').trim();
        if (postId.isEmpty || !(await _postExists(i, postId))) {
          throw localDomainCloudException(
            'CONTENT.USER.content_reaction_target_not_found',
          );
        }
        final actor = _actor(i);
        final key = i.store.reactionKey(actor, postId);
        final old = i.store.reactions[key];
        final changed = old?['liked'] != liked;
        final version =
            ((old?['version'] as num?)?.toInt() ?? 0) + (changed ? 1 : 0);
        i.store.reactions[key] = {
          'reactionId': old?['reactionId'] ?? i.nextId('rxn_'),
          'postId': postId,
          'actorId': actor,
          'liked': liked,
          'version': version == 0 ? 1 : version,
        };
        return {
          'reactionId': i.store.reactions[key]!['reactionId'],
          'postId': postId,
          'version': version == 0 ? 1 : version,
          'liked': liked,
          'changed': changed,
          'replayed': !changed,
        };
      });

  Future<bool> _postExists(RehearsalInvocation i, String id) async {
    if (i.store.records['content.local_posts']?.containsKey(id) == true ||
        i.store.records['content.post_targets']?.containsKey(id) == true) {
      return true;
    }
    return await postExists?.call(id) ?? false;
  }

  Future<Object?> _reactionState(RehearsalInvocation i) async {
    final postId = i.path('postId').trim();
    if (postId.isEmpty) {
      throw localDomainCloudException('CONTENT.USER.invalid_argument');
    }
    final row = i.store.reactions[i.store.reactionKey(_actor(i), postId)];
    return {
      'found': row != null,
      'postId': postId,
      'liked': row?['liked'] == true,
      'version': row?['version'] ?? 1,
    };
  }

  Future<Object?> _createComment(RehearsalInvocation i) {
    i.requireActor();
    return i.store.commit(() async {
      final postId = i.path('postId').trim();
      final content = '${i.body['content'] ?? ''}'.trim();
      if (postId.isEmpty || !(await _postExists(i, postId))) {
        throw localDomainCloudException('CONTENT.USER.post_not_found');
      }
      if (content.isEmpty) {
        throw localDomainCloudException('CONTENT.USER.invalid_argument');
      }
      final parent = '${i.body['replyToCommentId'] ?? ''}'.trim();
      if (parent.isNotEmpty && !i.store.comments.containsKey(parent)) {
        throw localDomainCloudException('CONTENT.USER.comment_parent_invalid');
      }
      final id = i.nextId('cmt_');
      final now = i.now().toUtc().toIso8601String();
      i.store.comments[id] = {
        'id': id,
        'version': 1,
        'postId': postId,
        'authorId': i.actorId,
        'content': content,
        if (parent.isNotEmpty) 'replyToCommentId': parent,
        if (parent.isNotEmpty) 'parentCommentId': parent,
        'attachmentMediaIds': List<Object?>.from(
          (i.body['attachmentMediaIds'] as List?) ?? const [],
        ),
        'attachments': <Object>[],
        'mentions': List<Object?>.from(
          (i.body['mentions'] as List?) ?? const [],
        ),
        'assistantMentioned': false,
        'status': 'active',
        'isPinned': false,
        'createdAt': now,
        'updatedAt': now,
        'replyCount': 0,
        'replyPreview': <Object>[],
        'likeCount': 0,
        'dislikeCount': 0,
        'viewerReaction': 'none',
        'authorLiked': false,
        'viewerRelation': 'none',
        'isAuthor': true,
        'canDelete': true,
        'canReply': true,
        'canReport': false,
        'canPin': false,
      };
      if (parent.isNotEmpty) {
        i.store.comments[parent]!['replyCount'] =
            ((i.store.comments[parent]!['replyCount'] as int?) ?? 0) + 1;
      }
      return {'id': id, 'version': 1, 'status': 'active', 'replayed': false};
    });
  }

  Future<Object?> _deleteComment(RehearsalInvocation i) =>
      _mutateOwnedComment(i, (row) {
        if (row['status'] == 'deleted') {
          return {
            'id': row['id'],
            'version': row['version'],
            'status': 'deleted',
            'replayed': true,
          };
        }
        row['status'] = 'deleted';
        row['deletedAt'] = i.now().toUtc().toIso8601String();
        row['version'] = (row['version'] as int) + 1;
        return {
          'id': row['id'],
          'version': row['version'],
          'status': 'deleted',
          'replayed': false,
        };
      });

  Future<Object?> _pinComment(RehearsalInvocation i, {required bool pinned}) =>
      _mutateOwnedComment(i, (row) {
        final changed = row['isPinned'] != pinned;
        if (changed) row['version'] = (row['version'] as int) + 1;
        row['isPinned'] = pinned;
        row['pinnedAt'] = pinned ? i.now().toUtc().toIso8601String() : null;
        return {
          'id': row['id'],
          'version': row['version'],
          'status': row['status'],
          'replayed': !changed,
        };
      });

  Future<Object?> _mutateOwnedComment(
    RehearsalInvocation i,
    Object? Function(Map<String, Object?>) mutate,
  ) {
    i.requireActor();
    return i.store.commit(() {
      final row = i.store.comments[i.path('commentId')];
      if (row == null) {
        throw localDomainCloudException('CONTENT.USER.comment_not_found');
      }
      if (row['authorId'] != i.actorId) {
        throw localDomainCloudException(
          'CONTENT.USER.comment_forbidden_delete',
        );
      }
      return mutate(row);
    });
  }

  Future<Object?> _bindCommentMedia(RehearsalInvocation i) =>
      _mutateOwnedComment(i, (row) {
        final ids = List<Object?>.from(
          (i.body['attachmentMediaIds'] as List?) ?? const [],
        );
        row['attachmentMediaIds'] = ids;
        row['version'] = (row['version'] as int) + 1;
        row['updatedAt'] = i.now().toUtc().toIso8601String();
        return {
          'id': row['id'],
          'version': row['version'],
          'status': row['status'],
          'replayed': false,
        };
      });

  Future<Object?> _reactComment(RehearsalInvocation i) {
    i.requireActor();
    return i.store.commit(() {
      final id = i.path('commentId');
      final comment = i.store.comments[id];
      if (comment == null || comment['status'] == 'deleted') {
        throw localDomainCloudException(
          'CONTENT.USER.content_reaction_target_not_found',
        );
      }
      final reaction = '${i.body['reaction'] ?? ''}';
      if (!const {'none', 'like', 'dislike'}.contains(reaction)) {
        throw localDomainCloudException('CONTENT.USER.invalid_argument');
      }
      final table = _table(i, 'content.comment_reactions');
      final key = '${i.actorId}::$id';
      final old = table[key];
      final previous = old?['reaction'] ?? 'none';
      final changed = previous != reaction;
      if (changed) {
        if (previous != 'none') {
          comment['${previous}Count'] =
              ((comment['${previous}Count'] as int?) ?? 1) - 1;
        }
        if (reaction != 'none') {
          comment['${reaction}Count'] =
              ((comment['${reaction}Count'] as int?) ?? 0) + 1;
        }
      }
      final version = ((old?['version'] as int?) ?? 0) + (changed ? 1 : 0);
      table[key] = {
        'reactionId': old?['reactionId'] ?? i.nextId('crx_'),
        'reaction': reaction,
        'version': version == 0 ? 1 : version,
      };
      return {
        'reactionId': table[key]!['reactionId'],
        'version': table[key]!['version'],
        'reaction': reaction,
        'changed': changed,
        'replayed': !changed,
        'likeCount': comment['likeCount'],
        'dislikeCount': comment['dislikeCount'],
      };
    });
  }

  Future<Object?> _listComments(RehearsalInvocation i) async {
    final id = i.operation.canonicalOperationId;
    if (id.contains('ByAuthor') || id.contains('ForPostAuthor')) {
      i.requireActor();
    }
    Iterable<Map<String, Object?>> rows = i.store.comments.values.where(
      (r) => r['status'] != 'deleted',
    );
    if (id.endsWith('ListComments')) {
      rows = rows.where(
        (r) => r['postId'] == i.path('postId') && r['replyToCommentId'] == null,
      );
    }
    if (id.endsWith('ListCommentReplies')) {
      rows = rows.where((r) => r['replyToCommentId'] == i.path('commentId'));
    }
    if (id.endsWith('ListCommentsByAuthor')) {
      rows = rows.where((r) => r['authorId'] == i.actorId);
    }
    if (id.endsWith('ListCommentsForPostAuthor')) {
      rows = rows.where((r) => r['authorId'] != i.actorId);
    }
    final all = rows.toList()
      ..sort((a, b) => '${b['createdAt']}'.compareTo('${a['createdAt']}'));
    final page = _page(
      i,
      all,
      defaultLimit: id.endsWith('ListCommentReplies') ? 10 : 20,
      max: 100,
    );
    return {
      'items': page.items
          .map(
            (r) => {
              ...r,
              'isAuthor': r['authorId'] == i.actorId,
              'canDelete': r['authorId'] == i.actorId,
              'canReport': r['authorId'] != i.actorId,
            },
          )
          .toList(),
      if (page.next != null) 'nextCursor': page.next,
      'total': all.length,
    };
  }

  Future<Object?> _reportBehaviors(RehearsalInvocation i) => i.store.commit(() {
    final events = i.body['events'];
    if (events is! List || events.isEmpty) {
      throw localDomainCloudException('CONTENT.USER.invalid_argument');
    }
    final table = _table(i, 'content.behaviors');
    var accepted = 0, replayed = 0;
    for (final raw in events) {
      if (raw is! Map) {
        throw localDomainCloudException('CONTENT.USER.invalid_argument');
      }
      final row = Map<String, Object?>.from(raw);
      final key = '${_actor(i)}::${row['eventId'] ?? jsonEncode(row)}';
      if (table.containsKey(key)) {
        replayed++;
      } else {
        table[key] = {...row, 'actorId': _actor(i)};
        accepted++;
      }
    }
    return {'acceptedCount': accepted, 'replayedCount': replayed};
  });

  Future<Object?> _getMedia(RehearsalInvocation i) async {
    final id = i.path('mediaId');
    final bundle = await OfflineContentBundle.load();
    Map<String, Object?>? row;
    for (final candidate in bundle.rows('media')) {
      if (candidate['assetId'] == id) {
        row = candidate;
        break;
      }
    }
    if (row == null) {
      throw localDomainCloudException('CONTENT.USER.media_not_found');
    }
    final kind = '${row['kind']}';
    return {
      'assetId': id,
      'version': row['version'],
      'mediaType': kind == 'video' ? 'video' : 'image',
      'mimeType': row['mimeType'],
      'fileSize': row['byteLength'],
      'status': 'ready',
      'accessPolicy': 'public',
      'imageWidth': row['width'],
      'imageHeight': row['height'],
      'imageDeliveryMimeType': row['mimeType'],
      'cdnUrl': row['canonicalReference'],
    };
  }

  Future<Object?> _appendShare(RehearsalInvocation i) => i.store.commit(() {
    final postId = i.path('postId'),
        referral = '${i.body['referralId'] ?? ''}',
        receipt = '${i.body['providerReceiptId'] ?? ''}';
    if (postId.isEmpty || referral.isEmpty || receipt.isEmpty) {
      throw localDomainCloudException('CONTENT.USER.invalid_argument');
    }
    final table = _table(i, 'content.outbound_shares'),
        key = '${_actor(i)}::$receipt',
        old = table[key];
    if (old != null) return {...old, 'replayed': true};
    final row = <String, Object?>{
      'eventId': i.nextId('share_'),
      'postId': postId,
      'channel': i.body['channel'],
      'referralId': referral,
      'occurredAt':
          i.body['clientConfirmedAt'] ?? i.now().toUtc().toIso8601String(),
      'replayed': false,
      'actorId': _actor(i),
      'destinationKind': i.body['destinationKind'],
    };
    table[key] = row;
    return row;
  });

  Future<Object?> _getPost(RehearsalInvocation i) async {
    final id = i.path('postId');
    final deleted = _table(i, 'content.posts')[id];
    if (deleted?['status'] == 'deleted') {
      throw localDomainCloudException('CONTENT.USER.content_deleted');
    }
    final bundle = await OfflineContentBundle.load();
    Map<String, Object?>? post;
    for (final row in bundle.rows('posts')) {
      final detail = Map<String, Object?>.from(row['detail'] as Map);
      if (detail['postId'] == id) {
        post = detail;
        break;
      }
    }
    post ??= _table(i, 'content.local_posts')[id];
    if (post == null) {
      throw localDomainCloudException('CONTENT.USER.post_not_found');
    }
    return const AlphaPostIntersectionProjector().project(
      post: post,
      viewerId: i.actorId,
      store: i.store,
      now: i.now(),
    );
  }

  Future<Object?> _getFeed(RehearsalInvocation i) async {
    var posts = await _bundlePosts(i);
    final channel = i.query('channelId');
    if (channel.isNotEmpty) {
      final bundle = await OfflineContentBundle.load();
      final channels = bundle.rows('channels');
      final c = channels
          .cast<Map<String, Object?>>()
          .where((x) => x['channelId'] == channel)
          .firstOrNull;
      if (c != null) {
        final order = List<String>.from(c['orderedPostIds'] as List);
        posts.sort(
          (a, b) => order
              .indexOf('${a['postId']}')
              .compareTo(order.indexOf('${b['postId']}')),
        );
      }
    }
    final page = _page(i, posts, defaultLimit: 20, max: 20);
    final projected = page.items
        .map(
          (p) => const AlphaPostIntersectionProjector().project(
            post: p,
            viewerId: i.actorId,
            store: i.store,
            now: i.now(),
          ),
        )
        .toList();
    return {
      'items': projected,
      'outcome': projected.isEmpty ? 'empty' : 'success',
      if (projected.isEmpty) 'emptyReason': 'no_content',
      if (page.next != null) 'nextCursor': page.next,
      'feedRequestId': i.query('feedRequestId').isEmpty
          ? i.nextId('feed_')
          : i.query('feedRequestId'),
      'objectCards': <Object>[],
    };
  }

  Future<Object?> _listUserPosts(RehearsalInvocation i) async {
    i.requireActor();
    final author = i.path('personaId');
    if (author.isEmpty || author == 'me') {
      throw localDomainCloudException('CONTENT.USER.invalid_argument');
    }
    final posts = (await _bundlePosts(i))
        .where((p) => p['authorId'] == author)
        .toList();
    final page = _page(i, posts, defaultLimit: 20, max: 100);
    return {
      'items': page.items
          .map(
            (p) => const AlphaPostIntersectionProjector().project(
              post: p,
              viewerId: i.actorId,
              store: i.store,
              now: i.now(),
            ),
          )
          .toList(),
      if (page.next != null) 'nextCursor': page.next,
      'hasMore': page.next != null,
    };
  }

  Future<Object?> _deletePost(RehearsalInvocation i) {
    i.requireActor();
    return i.store.commit(() async {
      final id = i.path('postId');
      final post = await _getPost(i) as Map<String, Object?>;
      if (post['authorId'] != i.actorId) {
        throw localDomainCloudException('CONTENT.USER.forbidden_delete');
      }
      _table(i, 'content.posts')[id] = {'postId': id, 'status': 'deleted'};
      return {'postId': id, 'status': 'deleted', 'replayed': false};
    });
  }

  Future<Object?> _footprint(RehearsalInvocation i) async {
    i.requireActor();
    final rows = _table(i, 'content.behaviors').values
        .where((r) => r['actorId'] == i.actorId && r['postId'] != null)
        .map(
          (r) => {
            'postId': r['postId'],
            'action': r['type'] ?? r['action'] ?? 'view',
            'occurredAt': r['occurredAt'] ?? i.now().toUtc().toIso8601String(),
          },
        )
        .toList();
    final page = _page(i, rows, defaultLimit: 20, max: 100);
    return {
      'items': page.items,
      if (page.next != null) 'nextCursor': page.next,
    };
  }

  Future<Object?> _saveCollection(RehearsalInvocation i) {
    i.requireActor();
    return i.store.commit(() {
      final id = i.path('collectionId'),
          table = _table(i, 'content.collections'),
          old = table[id];
      final expected = (i.body['expectedVersion'] as num?)?.toInt() ?? 0;
      if (old != null && old['ownerPersonaId'] != i.actorId) {
        throw localDomainCloudException(
          'CONTENT.USER.post_collection_unauthorized',
        );
      }
      if (old != null && old['version'] != expected) {
        throw localDomainCloudException(
          'CONTENT.USER.post_collection_version_conflict',
        );
      }
      final version = (old?['version'] as int? ?? 0) + 1;
      table[id] = {
        'collectionId': id,
        'ownerPersonaId': i.actorId,
        'name': i.body['name'],
        'coverAssetId': i.body['coverAssetId'],
        'visibility': i.body['visibility'],
        'version': version,
        'postIds': List<Object?>.from((i.body['postIds'] as List?) ?? const []),
        'status': 'active',
      };
      return {'collectionId': id, 'version': version, 'status': 'active'};
    });
  }

  Future<Object?> _deleteCollection(RehearsalInvocation i) {
    i.requireActor();
    return i.store.commit(() {
      final row = _table(i, 'content.collections')[i.path('collectionId')];
      if (row == null) {
        throw localDomainCloudException(
          'CONTENT.USER.post_collection_unavailable',
        );
      }
      if (row['ownerPersonaId'] != i.actorId) {
        throw localDomainCloudException(
          'CONTENT.USER.post_collection_unauthorized',
        );
      }
      row['status'] = 'deleted';
      row['version'] = (row['version'] as int) + 1;
      return {
        'collectionId': row['collectionId'],
        'version': row['version'],
        'status': 'deleted',
      };
    });
  }

  Future<Object?> _getCollection(
    RehearsalInvocation i, {
    required bool management,
  }) async {
    if (management) i.requireActor();
    final vars = (i.body['variables'] as Map?) ?? const {};
    final id = '${vars['collectionId'] ?? i.path('collectionId')}';
    final row = _table(i, 'content.collections')[id];
    if (row == null || row['status'] == 'deleted') {
      throw localDomainCloudException(
        'CONTENT.USER.post_collection_unavailable',
      );
    }
    if ((management || row['visibility'] == 'private') &&
        row['ownerPersonaId'] != i.actorId) {
      throw localDomainCloudException(
        'CONTENT.USER.post_collection_unauthorized',
      );
    }
    final posts = {for (final p in await _bundlePosts(i)) '${p['postId']}': p};
    final members = List<String>.from(row['postIds'] as List)
        .map(
          (id) => management
              ? {
                  'postId': id,
                  'readable': posts.containsKey(id),
                  if (posts[id] != null) 'title': posts[id]!['title'],
                }
              : {
                  'postId': id,
                  'contentType': posts[id]?['contentType'] ?? 'unknown',
                  'title': posts[id]?['title'] ?? '不可用',
                },
        )
        .toList();
    if (management) {
      return {
        'collectionId': id,
        'name': row['name'],
        'coverAssetId': row['coverAssetId'],
        'visibility': row['visibility'],
        'version': row['version'],
        'members': members,
      };
    }
    return {
      'collectionId': id,
      'ownerPersonaId': row['ownerPersonaId'],
      'name': row['name'],
      'coverAssetId': row['coverAssetId'],
      'visibility': row['visibility'],
      'version': row['version'],
      'members': members,
      'visibleCount': members.length,
      'canManage': row['ownerPersonaId'] == i.actorId,
    };
  }

  Future<Object?> _listInteractions(
    RehearsalInvocation i, {
    required bool received,
  }) async {
    i.requireActor();
    final persona = i.path('personaId');
    if (persona != i.actorId) {
      throw localDomainCloudException(
        'CONTENT.USER.interaction_owner_forbidden',
      );
    }
    final rows = _table(i, 'content.interactions').values
        .where(
          (r) => received
              ? r['targetPersonaId'] == persona
              : r['actorPersonaId'] == persona,
        )
        .toList();
    final page = _page(i, rows, defaultLimit: 20, max: 50);
    return {
      'items': page.items,
      if (page.next != null) 'nextCursor': page.next,
      'hasMore': page.next != null,
    };
  }

  Future<Object?> _readInteraction(RehearsalInvocation i) {
    i.requireActor();
    return i.store.commit(() {
      final persona = i.path('personaId'), activity = i.path('interactionId');
      if (persona != i.actorId) {
        throw localDomainCloudException(
          'CONTENT.USER.profile_interaction_read_fact_owner_forbidden',
        );
      }
      final row = _table(i, 'content.interactions')[activity];
      if (row == null || row['targetPersonaId'] != persona) {
        throw localDomainCloudException(
          'CONTENT.SYSTEM.profile_interaction_read_fact_target_unavailable',
        );
      }
      final state = '${i.body['state']}';
      final now = i.now().toUtc().toIso8601String();
      row[state == 'read' ? 'readAt' : 'seenAt'] = now;
      return {
        'factId': i.nextId('read_'),
        'activityId': activity,
        'state': state,
        'occurredAt': now,
        'replayed': false,
      };
    });
  }

  Future<Object?> _createReport(RehearsalInvocation i) {
    i.requireActor();
    return i.store.commit(() {
      final target = '${i.body['targetId'] ?? ''}';
      if (target.isEmpty) {
        throw localDomainCloudException('CONTENT.USER.invalid_argument');
      }
      final id = i.nextId('report_'), now = i.now().toUtc().toIso8601String();
      _table(i, 'content.reports')[id] = {
        'id': id,
        'reporterId': i.actorId,
        'targetType': i.body['targetType'],
        'targetId': target,
        'reason': i.body['reason'],
        'description': i.body['description'],
        'status': 'submitted',
        'createdAt': now,
        'updatedAt': now,
        'version': 1,
      };
      return {'id': id, 'version': 1, 'status': 'submitted', 'replayed': false};
    });
  }

  Future<Object?> _listReports(RehearsalInvocation i) async {
    i.requireActor();
    final rows =
        _table(
            i,
            'content.reports',
          ).values.where((r) => r['reporterId'] == i.actorId).toList()
          ..sort((a, b) => '${b['createdAt']}'.compareTo('${a['createdAt']}'));
    final page = _page(i, rows, defaultLimit: 20, max: 100);
    return {
      'items': page.items
          .map(
            (r) => Map<String, Object?>.from(r)
              ..remove('reporterId')
              ..remove('version'),
          )
          .toList(),
      if (page.next != null) 'nextCursor': page.next,
    };
  }

  _Page<T> _page<T>(
    RehearsalInvocation i,
    List<T> rows, {
    required int defaultLimit,
    required int max,
  }) {
    final limit =
        int.tryParse(i.query('limit')) ??
        ((i.body['variables'] as Map?)?['first'] as int?) ??
        defaultLimit;
    if (limit < 1 || limit > max) {
      throw localDomainCloudException('CONTENT.USER.invalid_argument');
    }
    final cursor = i.query('cursor').isNotEmpty
        ? i.query('cursor')
        : '${(i.body['variables'] as Map?)?['after'] ?? ''}';
    var offset = 0;
    if (cursor.isNotEmpty) {
      try {
        offset = int.parse(
          utf8.decode(base64Url.decode(base64Url.normalize(cursor))),
        );
      } catch (_) {
        throw localDomainCloudException('CONTENT.USER.invalid_argument');
      }
      if (offset < 0 || offset > rows.length) {
        throw localDomainCloudException('CONTENT.USER.invalid_argument');
      }
    }
    final end = (offset + limit).clamp(0, rows.length);
    return _Page(
      rows.sublist(offset, end),
      end < rows.length
          ? base64Url.encode(utf8.encode('$end')).replaceAll('=', '')
          : null,
    );
  }
}

final class _Page<T> {
  const _Page(this.items, this.next);
  final List<T> items;
  final String? next;
}
