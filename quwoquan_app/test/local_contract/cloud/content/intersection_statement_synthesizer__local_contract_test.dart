import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';

/// SVO displayBinding 展示合同（CR-20260715-105）+ V1 host_plain 投影收口。
///
/// 覆盖：
/// - explicit_link reason 在宿主上下文直出会被 self-link 校验淘汰（既有红线）；
/// - `applyHostPlainDisplayContext` 与云侧 `plainHostObjectSpan` 同构转换后，
///   同一 reason 在宿主上下文变为可展示（四主页卡 alpha 恒空的 V1 修复）；
/// - 非宿主 reason 不受转换影响；join(spans)==primaryText 不变量保持。
void main() {
  IntersectionTarget hostTarget() => IntersectionTarget(
    objectType: 'homepage',
    objectId: 'fixture_homepage_travel_route_erhai',
    objectKind: 'place',
    routeId: 'homepageDetail',
  );

  IntersectionReason seedReason() => IntersectionReason(
    intersectionId: 'ix_erhai_visit',
    intersectionClass: 'fact',
    dimension: 'location',
    objectKind: 'place',
    actionTargetId: 'fixture_homepage_travel_route_erhai',
    primaryText: '联系人林清越等3人来过「洱海环线」',
    displayBinding: 'explicit_link',
    actorEvidenceTotalCount: 3,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: 'fixture_user_lin',
      displayName: '林清越',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: IntersectionTarget(
        objectType: 'user',
        objectId: 'fixture_user_lin',
        objectKind: 'person',
        routeId: 'userProfile',
      ),
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
      IntersectionTextSpan(text: '等3人来过', role: 'plain'),
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

  test('applyHostPlainDisplayContext 与云侧 plainHostObjectSpan 同构：宿主页转换后可展示', () {
    final projected = applyHostPlainDisplayContext(seedReason(), hostTarget());

    expect(projected.displayBinding, 'host_plain');
    expect(projected.primaryText, seedReason().primaryText, reason: 'G2 主句不变');
    expect(
      projected.primarySpans.map((s) => s.text).join(),
      projected.primaryText,
      reason: 'join(spans)==primaryText 不变量',
    );
    final hostSpan = projected.primarySpans.firstWhere(
      (s) => s.text == '「洱海环线」',
    );
    expect(hostSpan.role, 'plain', reason: '宿主 span 降级为 plain');
    expect(hostSpan.target, isNull, reason: '宿主 span 去链接');
    final actorSpan = projected.primarySpans.firstWhere((s) => s.text == '林清越');
    expect(actorSpan.role, 'object', reason: '代表人 span 保持可点击');

    expect(
      displayReadyIntersectionReason(
        projected,
        contextObjectTarget: hostTarget(),
      ),
      isNotNull,
      reason: 'host_plain 转换后在宿主上下文必须可展示（V1 修复验收）',
    );
  });

  test('非宿主 reason 不受 host_plain 转换影响', () {
    final other = seedReason().copyWith(
      actionTargetId: 'fixture_homepage_other',
    );
    final projected = applyHostPlainDisplayContext(other, hostTarget());
    expect(projected.displayBinding, other.displayBinding);
    expect(
      projected.primarySpans.map((s) => s.role),
      other.primarySpans.map((s) => s.role),
    );
  });
}
