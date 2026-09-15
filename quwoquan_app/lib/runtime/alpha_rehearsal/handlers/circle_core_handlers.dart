import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/circle_handler_support.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';

final class CircleCoreRehearsalHandler {
  const CircleCoreRehearsalHandler();

  Future<Object?> handle(RehearsalInvocation i) =>
      switch (i.operation.canonicalOperationId) {
        'circle.circle.CreateCircle' => _create(i),
        'circle.circle.GetCircle' => _get(i),
        'circle.circle.UpdateCircle' => _update(i),
        'circle.circle.UpdateCircleSections' => _update(i),
        'circle.circle.ArchiveCircle' => _archive(i),
        'circle.circle.ListCircles' => _list(i),
        'circle.circle.ListCircleDiscoveryFeed' => _discovery(i),
        'circle.circle.SearchCircles' => _search(i),
        'circle.circle.GetCircleFeed' => _feed(i),
        'circle.circle.GetCircleStats' => _stats(i),
        'circle.circle.GetCircleImpact' => _impact(i),
        'circle.circle_behavior_fact.ReportCircleBehavior' => _behavior(i),
        'circle.circle_file.CreateCircleFile' => _createFile(i),
        'circle.circle_file.GetCircleFile' => _getFile(i),
        'circle.circle_file.ListCircleFiles' => _listFiles(i),
        'circle.circle_file.UpdateCircleFile' => _updateFile(i),
        'circle.circle_file.DeleteCircleFile' => _deleteFile(i),
        _ => rehearsalUnsupported(),
      };

  Future<Object?> _create(RehearsalInvocation i) => i.store.commit(() {
    i.requireActor();
    final name = requiredCircleBody(i, 'name');
    final id = i.nextId('circle_');
    final now = nowWire(i);
    final row = <String, Object?>{
      'id': id,
      'name': name,
      'ownerId': i.actorId,
      for (final key in [
        'description',
        'rulesText',
        'welcomeMessage',
        'coverUrl',
        'iconUrl',
        'category',
        'subCategory',
        'linkedHomepageId',
        'linkedHomepageType',
        'linkedHomepageTitle',
      ])
        if (i.body[key] != null) key: i.body[key],
      'tags': i.body['tags'] ?? const <Object>[],
      'memberCount': 1,
      'postCount': 0,
      'weeklyActiveCount': 1,
      'version': 1,
      'status': 'active',
      'visibility': i.body['visibility'] ?? 'public',
      'joinPolicy': i.body['joinPolicy'] ?? 'open',
      'kind': i.body['kind'] ?? 'interest',
      'displaySubjectType': i.body['displaySubjectType'] ?? 'circle',
      'followEnabled': i.body['followEnabled'] ?? true,
      'autoSyncChat': i.body['autoSyncChat'] ?? false,
      'storageUsedBytes': 0,
      'storageQuotaBytes': 1073741824,
      'createdAt': now,
      'updatedAt': now,
    };
    circleTable(i, 'circles')[id] = row;
    circleTable(i, 'memberships')[circleMembershipKey(id, i.actorId)] = {
      'membershipId': i.nextId('cm_'),
      'version': 1,
      'circleId': id,
      'personaId': i.actorId,
      'role': 'owner',
      'state': 'active',
      'joinedAt': now,
      'contribution': 0,
      'createdAt': now,
      'updatedAt': now,
    };
    return circleCommand(row);
  });

  Future<Object?> _get(RehearsalInvocation i) async {
    final row = requireRow(
      circleTable(i, 'circles'),
      requiredCirclePath(i, 'circleId'),
      'not_found',
    );
    if (row['status'] != 'active') circleFailure('not_found');
    return cloneRehearsalValue(row);
  }

  Future<Object?> _update(RehearsalInvocation i) => i.store.commit(() {
    final id = requiredCirclePath(i, 'circleId');
    final row = requireRow(circleTable(i, 'circles'), id, 'not_found');
    requireCircleManager(i, id);
    if (row['status'] != 'active') circleFailure('circle_archived');
    requireVersion(row, i.body['expectedVersion'], 'circle_version_conflict');
    if (i.operation.canonicalOperationId.endsWith('UpdateCircleSections')) {
      row['sectionConfig'] = cloneRehearsalValue(
        i.body['sectionConfig'] ?? i.body['sections'] ?? const <Object>[],
      );
    } else {
      for (final key in [
        'name',
        'description',
        'rulesText',
        'welcomeMessage',
        'coverUrl',
        'iconUrl',
        'category',
        'subCategory',
        'tags',
        'visibility',
        'joinPolicy',
        'followEnabled',
        'autoSyncChat',
        'linkedHomepageId',
        'linkedHomepageType',
        'linkedHomepageTitle',
      ]) {
        if (i.body.containsKey(key))
          row[key] = cloneRehearsalValue(i.body[key]);
      }
    }
    row['version'] = rowVersion(row) + 1;
    row['updatedAt'] = nowWire(i);
    return circleCommand(row);
  });

  Future<Object?> _archive(RehearsalInvocation i) => i.store.commit(() {
    final id = requiredCirclePath(i, 'circleId');
    final row = requireRow(circleTable(i, 'circles'), id, 'not_found');
    if (row['ownerId'] != i.actorId) circleFailure('permission_denied');
    row['status'] = 'archived';
    row['version'] = rowVersion(row) + 1;
    row['updatedAt'] = nowWire(i);
    return circleCommand(row);
  });

  Iterable<Map<String, Object?>> _visible(RehearsalInvocation i) =>
      circleTable(i, 'circles').values.where(
        (r) =>
            r['status'] == 'active' &&
            (r['visibility'] == 'public' || isCircleManager(i, '${r['id']}')),
      );
  Future<Object?> _list(RehearsalInvocation i) async => pageRows(
    i,
    _visible(i).where(
      (r) =>
          i.query('category').isEmpty || r['category'] == i.query('category'),
    ),
  );
  Future<Object?> _discovery(RehearsalInvocation i) async {
    final page = pageRows(i, _visible(i), maximum: 50);
    return {
      'circles': page['items'],
      'items': const <Object>[],
      if (page['cursor'] != null) 'cursor': page['cursor'],
    };
  }

  Future<Object?> _search(RehearsalInvocation i) async {
    final q = i.query('query').trim().toLowerCase();
    if (q.isEmpty) circleFailure('invalid_argument');
    final rows = _visible(i)
        .where(
          (r) => '${r['name']} ${r['description'] ?? ''}'
              .toLowerCase()
              .contains(q),
        )
        .map(
          (r) => {
            'circleId': r['id'],
            'name': r['name'],
            if (r['description'] != null) 'description': r['description'],
            if (r['coverUrl'] != null) 'coverUrl': r['coverUrl'],
            if (r['category'] != null) 'categoryId': r['category'],
            if (r['subCategory'] != null) 'subCategory': r['subCategory'],
            if (r['domainId'] != null) 'domainId': r['domainId'],
            'kind': r['kind'],
            'displaySubjectType': r['displaySubjectType'],
            'memberCount': r['memberCount'],
            'postCount': r['postCount'],
            'highlightText': q,
            'matchedField': 'name',
          },
        );
    final p = pageRows(i, rows, maximum: 100);
    return {
      'items': p['items'],
      'facetBuckets': const <Object>[],
      if (p['cursor'] != null) 'cursor': p['cursor'],
    };
  }

  Future<Object?> _feed(RehearsalInvocation i) async {
    final id = requiredCirclePath(i, 'circleId');
    requireRow(circleTable(i, 'circles'), id, 'not_found');
    return pageRows(
      i,
      circleTable(i, 'placements').values
          .where((r) => r['circleId'] == id && r['state'] == 'active')
          .map(
            (r) => {
              'circleId': id,
              'placementId': r['placementId'],
              'postId': r['postId'],
              'contentType': r['contentType'] ?? 'text',
              'authorVerified': false,
              'likeCount': 0,
              'commentCount': 0,
              'shareCount': 0,
              'createdAt': r['createdAt'],
              'updatedAt': r['updatedAt'],
              'pinned': r['pinned'] ?? false,
              'featured': r['featured'] ?? false,
              if (r['pinnedAt'] != null) 'pinnedAt': r['pinnedAt'],
              if (r['featuredAt'] != null) 'featuredAt': r['featuredAt'],
            },
          ),
    );
  }

  Future<Object?> _stats(RehearsalInvocation i) async {
    final id = requiredCirclePath(i, 'circleId');
    final r = requireRow(circleTable(i, 'circles'), id, 'not_found');
    return {
      'circleId': id,
      'memberCount': r['memberCount'],
      'postCount': r['postCount'],
      'discussionCount': 0,
      'weeklyActiveCount': r['weeklyActiveCount'],
      'likeCount': 0,
      'storageUsedBytes': r['storageUsedBytes'],
      'storageQuotaBytes': r['storageQuotaBytes'],
    };
  }

  Future<Object?> _impact(RehearsalInvocation i) async {
    final id = requiredCirclePath(i, 'circleId');
    requireRow(circleTable(i, 'circles'), id, 'not_found');
    return {'circleId': id, 'total': 0, 'items': const <Object>[]};
  }

  Future<Object?> _behavior(RehearsalInvocation i) => i.store.commit(() {
    final id = i.nextId('cbf_');
    circleTable(i, 'behavior_facts')[id] = {
      'id': id,
      ...i.body,
      'actorId': i.actorId,
      'createdAt': nowWire(i),
    };
    return {'accepted': true, 'id': id};
  });

  Future<Object?> _createFile(RehearsalInvocation i) => i.store.commit(() {
    final cid = requiredCirclePath(i, 'circleId');
    requireCircleMember(i, cid);
    final id = i.nextId('file_'), now = nowWire(i);
    final r = <String, Object?>{
      'fileId': id,
      'version': 1,
      'circleId': cid,
      if (i.body['groupId'] != null) 'groupId': i.body['groupId'],
      if (i.body['parentFolderId'] != null)
        'parentFolderId': i.body['parentFolderId'],
      'name': requiredCircleBody(i, 'name'),
      'fileType': i.body['fileType'] ?? 'file',
      if (i.body['assetId'] != null) 'assetId': i.body['assetId'],
      if (i.body['mimeType'] != null) 'mimeType': i.body['mimeType'],
      'sizeBytes': bodyInt(i, 'sizeBytes'),
      'uploaderPersonaId': i.actorId,
      'status': 'active',
      'createdAt': now,
      'updatedAt': now,
    };
    circleTable(i, 'files')[id] = r;
    return _fileCommand(r);
  });
  Future<Object?> _getFile(RehearsalInvocation i) async {
    final cid = requiredCirclePath(i, 'circleId');
    requireCircleMember(i, cid);
    final r = requireRow(
      circleTable(i, 'files'),
      requiredCirclePath(i, 'fileId'),
      'file_not_found',
    );
    if (r['circleId'] != cid || r['status'] != 'active')
      circleFailure('file_not_found');
    return cloneRehearsalValue(r);
  }

  Future<Object?> _listFiles(RehearsalInvocation i) async {
    final cid = requiredCirclePath(i, 'circleId');
    requireCircleMember(i, cid);
    return pageRows(
      i,
      circleTable(i, 'files').values.where(
        (r) =>
            r['circleId'] == cid &&
            r['status'] == 'active' &&
            (i.query('groupId').isEmpty || r['groupId'] == i.query('groupId')),
      ),
    );
  }

  Future<Object?> _updateFile(RehearsalInvocation i) => i.store.commit(() {
    final cid = requiredCirclePath(i, 'circleId'),
        fid = requiredCirclePath(i, 'fileId');
    requireCircleMember(i, cid);
    final r = requireRow(circleTable(i, 'files'), fid, 'file_not_found');
    if (r['uploaderPersonaId'] != i.actorId && !isCircleManager(i, cid))
      circleFailure('permission_denied');
    requireVersion(
      r,
      i.body['expectedVersion'] ?? i.payload.headers['If-Match'],
      'file_version_conflict',
    );
    for (final k in ['name', 'parentFolderId'])
      if (i.body.containsKey(k)) r[k] = i.body[k];
    r['version'] = rowVersion(r) + 1;
    r['updatedAt'] = nowWire(i);
    return _fileCommand(r);
  });
  Future<Object?> _deleteFile(RehearsalInvocation i) => i.store.commit(() {
    final cid = requiredCirclePath(i, 'circleId'),
        fid = requiredCirclePath(i, 'fileId');
    final r = requireRow(circleTable(i, 'files'), fid, 'file_not_found');
    if (r['uploaderPersonaId'] != i.actorId && !isCircleManager(i, cid))
      circleFailure('permission_denied');
    r['status'] = 'deleted';
    r['version'] = rowVersion(r) + 1;
    r['updatedAt'] = nowWire(i);
    return _fileCommand(r);
  });
  Map<String, Object?> _fileCommand(Map<String, Object?> r) => {
    'fileId': r['fileId'],
    'version': r['version'],
    'status': r['status'],
    'idempotentReplay': false,
  };
}
