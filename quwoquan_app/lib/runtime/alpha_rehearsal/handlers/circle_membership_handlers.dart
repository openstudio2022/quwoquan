import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/circle_handler_support.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';

final class CircleMembershipRehearsalHandler {
  const CircleMembershipRehearsalHandler();
  Future<Object?> handle(RehearsalInvocation i) {
    final id = i.operation.canonicalOperationId;
    if (id.startsWith('circle.circle_group_membership.'))
      return _groupMembership(i, id);
    if (id.startsWith('circle.circle_membership.')) return _membership(i, id);
    if (id.startsWith('circle.circle_group.')) return _group(i, id);
    if (id.startsWith('circle.circle_post_placement.'))
      return _placement(i, id);
    return rehearsalUnsupported();
  }

  Future<Object?> _membership(RehearsalInvocation i, String op) async {
    final t = circleTable(i, 'memberships');
    if (op.endsWith('ListPersonaCircles')) {
      final pid = requiredCirclePath(i, 'personaId');
      final circles = circleTable(i, 'circles');
      return pageRows(
        i,
        t.values
            .where((r) => r['personaId'] == pid && r['state'] == 'active')
            .map((r) {
              final c = circles[r['circleId']]!;
              return {
                'circleId': c['id'],
                'name': c['name'],
                if (c['description'] != null) 'description': c['description'],
                if (c['coverUrl'] != null) 'coverUrl': c['coverUrl'],
                if (c['iconUrl'] != null) 'iconUrl': c['iconUrl'],
                'ownerPersonaId': c['ownerId'],
                if (c['category'] != null) 'category': c['category'],
                if (c['subCategory'] != null) 'subCategory': c['subCategory'],
                'tags': c['tags'],
                'memberCount': c['memberCount'],
                'postCount': c['postCount'],
                'weeklyActiveCount': c['weeklyActiveCount'],
                'status': c['status'],
                'visibility': c['visibility'],
                'joinPolicy': c['joinPolicy'],
                'kind': c['kind'],
                'displaySubjectType': c['displaySubjectType'],
                'followEnabled': c['followEnabled'],
                if (c['defaultPublicGroupId'] != null)
                  'defaultPublicGroupId': c['defaultPublicGroupId'],
                'createdAt': c['createdAt'],
                'updatedAt': c['updatedAt'],
              };
            }),
      );
    }
    final cid = requiredCirclePath(i, 'circleId');
    if (op.endsWith('GetMyCircleMembership'))
      return cloneRehearsalValue(
        requireRow(
          t,
          circleMembershipKey(cid, i.actorId),
          'membership_not_found',
        ),
      );
    if (op.endsWith('ListCircleMemberships') ||
        op.endsWith('ListPendingCircleMemberships')) {
      if (op.endsWith('ListPendingCircleMemberships'))
        requireCircleManager(i, cid);
      final state = op.endsWith('ListPendingCircleMemberships')
          ? 'pending'
          : '';
      return pageRows(
        i,
        t.values.where(
          (r) => r['circleId'] == cid && (state.isEmpty || r['state'] == state),
        ),
      );
    }
    return i.store.commit(() {
      final t = circleTable(i, 'memberships');
      final target = i.path('personaId').isEmpty
          ? i.actorId
          : requiredCirclePath(i, 'personaId');
      final key = circleMembershipKey(cid, target);
      if (op.endsWith('JoinCircle')) {
        final circle = requireRow(circleTable(i, 'circles'), cid, 'not_found');
        final existing = t[key];
        if (existing?['state'] == 'active')
          circleFailure('membership_already_active');
        final now = nowWire(i),
            state = circle['joinPolicy'] == 'approval' ? 'pending' : 'active';
        final row = <String, Object?>{
          'membershipId': existing?['membershipId'] ?? i.nextId('cm_'),
          'version': rowVersion(existing ?? {}) + 1,
          'circleId': cid,
          'personaId': target,
          'role': 'member',
          'state': state,
          'joinedAt': now,
          'contribution': 0,
          'createdAt': existing?['createdAt'] ?? now,
          'updatedAt': now,
        };
        t[key] = row;
        if (state == 'active')
          circle['memberCount'] =
              ((circle['memberCount'] as num?)?.toInt() ?? 0) + 1;
        return membershipCommand(row);
      }
      final row =
          t[key] ??
          t.values
              .cast<Map<String, Object?>>()
              .where(
                (candidate) =>
                    candidate['circleId'] == cid &&
                    candidate['personaId'] == target,
              )
              .firstOrNull ??
          circleFailure('membership_not_found');
      if (op.endsWith('LeaveCircle')) {
        if (row['role'] == 'owner')
          circleFailure('membership_owner_cannot_leave');
        row['state'] = 'left';
        row['leftAt'] = nowWire(i);
      } else {
        requireCircleManager(i, cid);
        if (op.endsWith('ApproveCircleMember')) {
          if (row['state'] != 'pending')
            circleFailure('membership_state_conflict');
          row['state'] = 'active';
          row['joinedAt'] = nowWire(i);
        } else if (op.endsWith('RejectCircleMember')) {
          if (row['state'] != 'pending')
            circleFailure('membership_state_conflict');
          row['state'] = 'rejected';
        } else if (op.endsWith('UpdateCircleMembershipRole')) {
          final role = '${i.body['role'] ?? ''}';
          if (!const {'admin', 'member'}.contains(role))
            circleFailure('membership_role_invalid');
          row['role'] = role;
        }
      }
      row['version'] = rowVersion(row) + 1;
      row['updatedAt'] = nowWire(i);
      return membershipCommand(row);
    });
  }

  Future<Object?> _group(RehearsalInvocation i, String op) async {
    final cid = requiredCirclePath(i, 'circleId'), t = circleTable(i, 'groups');
    requireCircleMember(i, cid);
    if (op.endsWith('GetCircleGroup'))
      return cloneRehearsalValue(
        requireRow(t, requiredCirclePath(i, 'groupId'), 'group_not_found'),
      );
    if (op.endsWith('ListCircleGroups') || op.endsWith('SearchCircleGroups')) {
      final q = i.query('query').toLowerCase();
      return pageRows(
        i,
        t.values.where(
          (r) =>
              r['circleId'] == cid &&
              r['status'] == 'active' &&
              (q.isEmpty || '${r['name']}'.toLowerCase().contains(q)),
        ),
      );
    }
    return i.store.commit(() {
      final t = circleTable(i, 'groups');
      if (op.endsWith('CreateCircleGroup')) {
        final id = i.nextId('group_'), now = nowWire(i);
        final r = <String, Object?>{
          'groupId': id,
          'version': 1,
          'circleId': cid,
          if (i.body['parentGroupId'] != null)
            'parentGroupId': i.body['parentGroupId'],
          'groupType': i.body['groupType'] ?? 'self_built',
          if (i.body['nodeType'] != null) 'nodeType': i.body['nodeType'],
          'name': requiredCircleBody(i, 'name'),
          'description': i.body['description'] ?? '',
          'visibility': i.body['visibility'] ?? 'private',
          'joinPolicy': i.body['joinPolicy'] ?? 'apply_only',
          'storageEnabled': i.body['storageEnabled'] ?? false,
          'noticeEnabled': i.body['noticeEnabled'] ?? true,
          'isDefaultPublicGroup': false,
          'status': 'active',
          'memberCount': 1,
          'createdAt': now,
          'updatedAt': now,
        };
        t[id] = r;
        circleTable(i, 'group_memberships')[circleGroupMembershipKey(
          cid,
          id,
          i.actorId,
        )] = {
          'membershipId': i.nextId('cgm_'),
          'version': 1,
          'groupId': id,
          'circleId': cid,
          'personaId': i.actorId,
          'role': 'owner',
          'state': 'active',
          'joinedAt': now,
          'createdAt': now,
          'updatedAt': now,
        };
        return groupCommand(r);
      }
      final gid = requiredCirclePath(i, 'groupId'),
          r = requireRow(t, gid, 'group_not_found');
      requireGroupManager(i, cid, gid);
      if (op.endsWith('ArchiveCircleGroup'))
        r['status'] = 'archived';
      else {
        requireVersion(
          r,
          i.body['expectedVersion'] ?? i.payload.headers['If-Match'],
          'group_version_conflict',
        );
        for (final k in [
          'name',
          'description',
          'visibility',
          'joinPolicy',
          'storageEnabled',
          'noticeEnabled',
          'parentGroupId',
        ])
          if (i.body.containsKey(k)) r[k] = i.body[k];
      }
      r['version'] = rowVersion(r) + 1;
      r['updatedAt'] = nowWire(i);
      return groupCommand(r);
    });
  }

  Future<Object?> _groupMembership(RehearsalInvocation i, String op) async {
    final cid = requiredCirclePath(i, 'circleId'),
        gid = requiredCirclePath(i, 'groupId'),
        t = circleTable(i, 'group_memberships'),
        key = circleGroupMembershipKey(
          cid,
          gid,
          i.path('personaId').isEmpty ? i.actorId : i.path('personaId'),
        );
    requireCircleMember(i, cid);
    if (op.endsWith('GetMyCircleGroupMembership'))
      return cloneRehearsalValue(
        requireRow(
          t,
          circleGroupMembershipKey(cid, gid, i.actorId),
          'group_membership_not_found',
        ),
      );
    if (op.endsWith('ListCircleGroupMemberships')) {
      requireRow(circleTable(i, 'groups'), gid, 'group_not_found');
      return pageRows(
        i,
        t.values.where(
          (r) =>
              r['circleId'] == cid &&
              r['groupId'] == gid &&
              (i.query('state').isEmpty || r['state'] == i.query('state')),
        ),
      );
    }
    return i.store.commit(() {
      final t = circleTable(i, 'group_memberships');
      if (op.endsWith('ApplyJoinCircleGroup')) {
        final existing = t[key];
        if (existing?['state'] == 'active')
          circleFailure('group_membership_already_active');
        final now = nowWire(i),
            r = <String, Object?>{
              'membershipId': existing?['membershipId'] ?? i.nextId('cgm_'),
              'version': rowVersion(existing ?? {}) + 1,
              'groupId': gid,
              'circleId': cid,
              'personaId': i.actorId,
              'role': 'member',
              'state': 'pending',
              'createdAt': existing?['createdAt'] ?? now,
              'updatedAt': now,
            };
        t[key] = r;
        return groupMembershipCommand(r);
      }
      final r = requireRow(t, key, 'group_membership_not_found');
      if (op.endsWith('LeaveCircleGroup')) {
        if (r['role'] == 'owner')
          circleFailure('group_membership_owner_cannot_leave');
        r['state'] = 'left';
        r['leftAt'] = nowWire(i);
      } else {
        requireGroupManager(i, cid, gid);
        if (op.endsWith('ApproveCircleGroupMember')) {
          r['state'] = 'active';
          r['joinedAt'] = nowWire(i);
          r['decidedAt'] = nowWire(i);
        } else if (op.endsWith('RejectCircleGroupMember')) {
          r['state'] = 'rejected';
          r['decidedAt'] = nowWire(i);
        } else if (op.endsWith('RemoveCircleGroupMember')) {
          if (r['role'] == 'owner')
            circleFailure('group_membership_owner_cannot_remove');
          r['state'] = 'removed';
          r['leftAt'] = nowWire(i);
        } else {
          final role = '${i.body['role'] ?? ''}';
          if (!const {'manager', 'member'}.contains(role))
            circleFailure('group_membership_role_invalid');
          r['role'] = role;
        }
      }
      r['version'] = rowVersion(r) + 1;
      r['updatedAt'] = nowWire(i);
      return groupMembershipCommand(r);
    });
  }

  Future<Object?> _placement(RehearsalInvocation i, String op) =>
      i.store.commit(() {
        final cid = requiredCirclePath(i, 'circleId'),
            t = circleTable(i, 'placements');
        if (op.endsWith('PlacePostInCircle')) {
          requireCircleMember(i, cid);
          final post = requiredCircleBody(i, 'postId');
          if (t.values.any(
            (r) =>
                r['circleId'] == cid &&
                r['postId'] == post &&
                r['state'] == 'active',
          ))
            circleFailure('placement_already_exists');
          final id = i.nextId('placement_'),
              now = nowWire(i),
              r = <String, Object?>{
                'placementId': id,
                'version': 1,
                'circleId': cid,
                'postId': post,
                'contentType': i.body['contentType'] ?? 'text',
                'ownerId': i.actorId,
                'state': 'active',
                'pinned': false,
                'featured': false,
                'createdAt': now,
                'updatedAt': now,
              };
          t[id] = r;
          final c = requireRow(circleTable(i, 'circles'), cid, 'not_found');
          c['postCount'] = ((c['postCount'] as num?)?.toInt() ?? 0) + 1;
          return _placementCommand(r);
        }
        final id = requiredCirclePath(i, 'placementId'),
            r = requireRow(t, id, 'placement_not_found');
        if (r['ownerId'] != i.actorId && !isCircleManager(i, cid))
          circleFailure('permission_denied');
        if (op.endsWith('RemovePostFromCircle'))
          r['state'] = 'removed';
        else {
          requireCircleManager(i, cid);
          final field = op.endsWith('PinCirclePost') ? 'pinned' : 'featured';
          r[field] = i.body[field] ?? i.body['enabled'] ?? true;
          r['${field}At'] = r[field] == true ? nowWire(i) : null;
        }
        r['version'] = rowVersion(r) + 1;
        r['updatedAt'] = nowWire(i);
        return _placementCommand(r);
      });
  Map<String, Object?> _placementCommand(Map<String, Object?> r) => {
    'placementId': r['placementId'],
    'version': r['version'],
    'state': r['state'],
    'idempotentReplay': false,
  };
}
