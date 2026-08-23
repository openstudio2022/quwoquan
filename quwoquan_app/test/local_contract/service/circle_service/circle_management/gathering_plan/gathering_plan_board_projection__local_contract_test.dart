// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/adapters/gathering_plan_wire_codec.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

void main() {
  group('GatheringPlan 看板只读投影', () {
    test('看板读的是 current Revision，而不是编号最大的历史版本', () {
      final slice = gatheringBoardPlanFromWire(
        _plan(
          currentRevisionId: 'revision-2',
          currentRevisionNumber: 2,
          revisions: <cloud.PlanRevision>[
            _revision(
              revisionId: 'revision-2',
              revisionNumber: 2,
              items: <cloud.PlanItem>[
                _item(
                  itemId: 'item-note',
                  kind: cloud.PlanItemKind.note,
                  order: 1,
                  note: const cloud.PlanNoteItem(content: '当前版备注'),
                ),
              ],
            ),
            // 历史里存在编号更大的 Revision 时，current pointer 仍是唯一真相源。
            _revision(
              revisionId: 'revision-3',
              revisionNumber: 3,
              items: <cloud.PlanItem>[
                _item(
                  itemId: 'item-stale',
                  kind: cloud.PlanItemKind.note,
                  order: 1,
                  note: const cloud.PlanNoteItem(content: '不该出现'),
                ),
              ],
            ),
          ],
        ),
      );

      expect(slice.capability.state, GatheringBoardCapabilityState.available);
      expect(slice.items.single.title, '当前版备注');
      expect(slice.capability.itemCount, 1);
    });

    test('typed PlanItem 按 order 排序并逐类映射为看板条目', () {
      final slice = gatheringBoardPlanFromWire(
        _plan(
          currentRevisionId: 'revision-1',
          currentRevisionNumber: 1,
          revisions: <cloud.PlanRevision>[
            _revision(
              revisionId: 'revision-1',
              revisionNumber: 1,
              items: <cloud.PlanItem>[
                _item(
                  itemId: 'item-task',
                  kind: cloud.PlanItemKind.task,
                  order: 3,
                  task: cloud.PlanTaskItem(
                    content: '订车票',
                    dueAt: DateTime.utc(2026, 3, 4),
                    completed: true,
                  ),
                ),
                _item(
                  itemId: 'item-agenda',
                  kind: cloud.PlanItemKind.agenda,
                  order: 1,
                  agenda: cloud.PlanAgendaItem(
                    content: '集合出发',
                    startsAt: DateTime.utc(2026, 3, 5, 1, 30),
                    durationMinutes: 45,
                  ),
                ),
                _item(
                  itemId: 'item-checklist',
                  kind: cloud.PlanItemKind.checklist,
                  order: 2,
                  checklist: const cloud.PlanChecklistItem(
                    entries: <cloud.PlanChecklistEntry>[
                      cloud.PlanChecklistEntry(
                        entryId: 'entry-1',
                        content: '证件',
                        checked: true,
                      ),
                      cloud.PlanChecklistEntry(
                        entryId: 'entry-2',
                        content: '充电宝',
                        checked: false,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      );

      expect(
        slice.items.map((item) => item.planItemId).toList(growable: false),
        <String>['item-agenda', 'item-checklist', 'item-task'],
      );
      expect(slice.items[0].title, '集合出发');
      expect(slice.items[0].detail, contains('45 分钟'));
      expect(slice.items[1].detail, '已完成 1/2');
      expect(slice.items[1].completed, isFalse);
      expect(slice.items[2].title, '订车票');
      expect(slice.items[2].completed, isTrue);
      expect(slice.items[2].detail, contains('2026-03-04'));
    });

    test('place 与 route 只展示人工说明，不解析来源对象正文', () {
      final slice = gatheringBoardPlanFromWire(
        _plan(
          currentRevisionId: 'revision-1',
          currentRevisionNumber: 1,
          revisions: <cloud.PlanRevision>[
            _revision(
              revisionId: 'revision-1',
              revisionNumber: 1,
              items: <cloud.PlanItem>[
                _item(
                  itemId: 'item-place',
                  kind: cloud.PlanItemKind.place,
                  order: 1,
                  place: const cloud.PlanPlaceItem(
                    placeRef: cloud.GatheringPlanSourceRef(
                      objectTypeRef: 'entity.homepage',
                      objectId: 'homepage-west-lake',
                    ),
                  ),
                ),
                _item(
                  itemId: 'item-route',
                  kind: cloud.PlanItemKind.routeSegment,
                  order: 2,
                  routeSegment: const cloud.PlanRouteSegmentItem(
                    fromPlaceRef: cloud.GatheringPlanSourceRef(
                      objectTypeRef: 'entity.homepage',
                      objectId: 'homepage-station',
                    ),
                    toPlaceRef: cloud.GatheringPlanSourceRef(
                      objectTypeRef: 'entity.homepage',
                      objectId: 'homepage-west-lake',
                    ),
                    travelMode: cloud.PlanTravelMode.transit,
                    estimatedMinutes: 25,
                  ),
                ),
              ],
            ),
          ],
        ),
      );

      // 无 instruction 时退回类型标签，不得泄漏 objectId。
      expect(slice.items[0].title, '地点安排');
      expect(slice.items[0].title, isNot(contains('homepage')));
      expect(slice.items[1].title, '路线安排');
      expect(slice.items[1].detail, '公共交通 · 约 25 分钟');
    });

    test('current pointer 指不到已提交 Revision 时判失败，不塌陷成空计划', () {
      final slice = gatheringBoardPlanFromWire(
        _plan(
          currentRevisionId: 'revision-missing',
          currentRevisionNumber: 9,
          revisions: <cloud.PlanRevision>[
            _revision(
              revisionId: 'revision-1',
              revisionNumber: 1,
              items: const <cloud.PlanItem>[],
            ),
          ],
        ),
      );

      expect(slice.capability.state, GatheringBoardCapabilityState.unavailable);
      expect(
        slice.capability.unavailableReason,
        GatheringBoardCapabilityUnavailableReason.temporarilyUnavailable,
      );
      expect(slice.items, isEmpty);
    });

    test('计划不可读的三种原因各自可区分', () {
      for (final reason in <GatheringBoardCapabilityUnavailableReason>[
        GatheringBoardCapabilityUnavailableReason.notConfigured,
        GatheringBoardCapabilityUnavailableReason.permissionDenied,
        GatheringBoardCapabilityUnavailableReason.temporarilyUnavailable,
      ]) {
        final slice = gatheringBoardPlanUnavailable(reason, '标签');

        expect(slice.capability.unavailableReason, reason);
        expect(
          slice.capability.state,
          GatheringBoardCapabilityState.unavailable,
        );
        expect(slice.capability.unavailableLabel, '标签');
        expect(slice.items, isEmpty);
      }
    });
  });
}

cloud.GatheringPlan _plan({
  required String currentRevisionId,
  required int currentRevisionNumber,
  required List<cloud.PlanRevision> revisions,
}) => cloud.GatheringPlan(
  id: 'plan-1',
  gatheringId: 'gathering-1',
  version: 3,
  currentRevisionId: currentRevisionId,
  currentRevisionNumber: currentRevisionNumber,
  currentRevisionDigest: 'digest-$currentRevisionNumber',
  revisions: revisions,
  proposals: const <cloud.GatheringPlanProposal>[],
  acknowledgements: const <cloud.PlanRevisionAcknowledgement>[],
  createdAt: DateTime.utc(2026, 3, 1),
  updatedAt: DateTime.utc(2026, 3, 2),
);

cloud.PlanRevision _revision({
  required String revisionId,
  required int revisionNumber,
  required List<cloud.PlanItem> items,
}) => cloud.PlanRevision(
  revisionId: revisionId,
  revisionNumber: revisionNumber,
  baseRevisionNumber: revisionNumber - 1,
  baseRevisionDigest: 'digest-${revisionNumber - 1}',
  revisionDigest: 'digest-$revisionNumber',
  committedByPersonaId: 'persona-host',
  items: items,
  acknowledgementPolicy: const cloud.PlanAcknowledgementPolicy(
    mode: cloud.PlanAcknowledgementMode.none,
  ),
  affectedParticipationRefs: const <cloud.GatheringPlanParticipationRef>[],
  committedAt: DateTime.utc(2026, 3, 2),
);

cloud.PlanItem _item({
  required String itemId,
  required cloud.PlanItemKind kind,
  required int order,
  cloud.PlanAgendaItem? agenda,
  cloud.PlanPlaceItem? place,
  cloud.PlanRouteSegmentItem? routeSegment,
  cloud.PlanTaskItem? task,
  cloud.PlanChecklistItem? checklist,
  cloud.PlanNoteItem? note,
}) => cloud.PlanItem(
  itemId: itemId,
  kind: kind,
  order: order,
  agenda: agenda,
  place: place,
  routeSegment: routeSegment,
  task: task,
  checklist: checklist,
  note: note,
  sourceRefs: const <cloud.GatheringPlanSourceRef>[],
);
