# circle-feed-viewer-handoff-contract — tasks

## Current Slice

### P1: handoff contract freeze

- [x] T01: [helper] 新增 `media_viewer_result_absorber.dart` 统一 circle 来源 result 吸收逻辑
- [x] T02: [circle] 在 `section_creations.dart` 构造与 discovery 同构的 `MediaViewerInteractionSnapshot`
- [x] T03: [circle] handoff 时带入 `circleId`、`rawPostsById`、正文/互动快照

### P2: open and dismiss flow integration

- [x] T04: [circle] viewer 返回后通过统一 helper 回写 `liked/saved/following` 与最终计数
- [x] T05: [circle] 返回后同步 shared provider，避免 profile/viewer/circle 长期分叉
- [x] T06: [test] 新增 `media_viewer_result_absorb_test.dart`

### P3: align source of truth

- [x] T07: [circle] 来源渲染优先消费 `UserRelationshipStateProvider` / `PostInteractionStateProvider`
- [x] T08: [discovery] `home_page.dart` open/dismiss 也同步 shared provider，保持双来源协议一致

## Verification

- [x] V01: `flutter test test/ui/circle/widgets/media_viewer_result_absorb_test.dart`
- [x] V02: `make -C quwoquan_service build && make -C quwoquan_service test-contract`
