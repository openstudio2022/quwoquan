import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';

import '../../../support/fixtures/intersection_fixtures.dart';

/// SVO displayBinding 展示合同与 canonical host projection 边界。
///
/// 覆盖：
/// - explicit_link reason 在宿主上下文直出会被 self-link 校验淘汰（既有红线）；
/// - host_plain 必须由 Recommendation projection 下发；App 只校验、不改写 wire；
/// - 非宿主 reason 不受 host context 影响；join(spans)==primaryText 不变量保持。
void main() {
  IntersectionTarget hostTarget() => IntersectionTarget(
    objectType: 'homepage',
    objectId: 'fixture_homepage_travel_route_erhai',
    objectKind: 'place',
    routeId: 'homepageDetail',
  );

  IntersectionReason seedReason() => intersectionReasonFixture(
    intersectionId: 'ix_erhai_visit',
    intersectionClass: 'fact',
    dimension: 'location',
    objectKind: 'place',
    actionTargetId: 'fixture_homepage_travel_route_erhai',
    primaryText: '联系人林清越等3人也看过「洱海环线」',
    displayBinding: 'explicit_link',
    actorEvidenceTotalCount: 3,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: 'fixture_user_lin',
      displayName: '林清越',
      avatarUrl: '',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: IntersectionTarget(
        objectType: 'user',
        objectId: 'fixture_user_lin',
        objectKind: 'person',
        routeId: 'userProfile',
      ),
      evidenceRank: 1,
      snapshotVersion: 'intersection_fixture',
    ),
    primarySpans: <IntersectionTextSpan>[
      IntersectionTextSpan(text: '联系人', role: 'plain'),
      IntersectionTextSpan(
        text: '林清越',
        role: 'object',
        target: IntersectionTarget(
          objectType: 'user',
          objectId: 'fixture_user_lin',
          objectKind: 'person',
          routeId: 'userProfile',
        ),
      ),
      IntersectionTextSpan(text: '等3人也看过', role: 'plain'),
      IntersectionTextSpan(
        text: '「洱海环线」',
        role: 'object',
        target: IntersectionTarget(
          objectType: 'homepage',
          objectId: 'fixture_homepage_travel_route_erhai',
          objectKind: 'place',
          routeId: 'homepageDetail',
        ),
      ),
    ],
  );

  test('explicit_link seed 在宿主上下文直出必须被 self-link 校验淘汰（既有红线）', () {
    final reason = seedReason();
    expect(
      displayReadyIntersectionReason(reason),
      isNotNull,
      reason: '无宿主上下文（收件箱等）应可展示',
    );
    expect(
      displayReadyIntersectionReason(reason, contextObjectTarget: hostTarget()),
      isNull,
      reason: '宿主页直出 explicit_link + 宿主 self-link 必须 fail-closed',
    );
  });

  test('App 不把 explicit_link 改写成 host_plain', () {
    final projected = applyHostPlainDisplayContext(seedReason(), hostTarget());

    expect(projected.toWire(), seedReason().toWire());
    expect(projected.displayBinding, 'explicit_link');
    final hostSpan = projected.primarySpans.firstWhere(
      (s) => s.text == '「洱海环线」',
    );
    expect(hostSpan.role, 'object');
    expect(hostSpan.target, isNotNull);

    expect(
      displayReadyIntersectionReason(
        projected,
        contextObjectTarget: hostTarget(),
      ),
      isNull,
      reason: '服务未投影 host_plain 时 App 必须 fail-closed，不能本地修补',
    );
  });

  test('非宿主 reason 同样保持 canonical wire 不变', () {
    final other = copyIntersectionReasonFixture(
      seedReason(),
      actionTargetId: 'fixture_homepage_other',
    );
    final projected = applyHostPlainDisplayContext(other, hostTarget());
    expect(projected.toWire(), other.toWire());
  });
}
