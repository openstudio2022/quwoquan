/// T4 Patrol E2E: 首页推荐用户旅程（阶段9 商用化收口）
///
/// 对应 AppRoot Journey：发现/推荐主路径。本用例在真实设备 + 真实 gamma 后端
/// 上守护 flutter_test 无法替代的端到端行为：真实远端 feed 渲染、真实导航进入
/// 沉浸消费再返回、真实负反馈行为上报与即时收敛、真实作者对象跳转。
///
/// 与 T2 的映射（R12 一体性）：
///   - 多形态卡片 / 交集证据行渲染   <- home_intersection_multiform_feed_widget_test
///   - 交集 name-span→主页 / count-span→交集列表 的精确导航
///                                    <- home_intersection_object_nav_test
///                                       intersection_target_navigator_test
///   - 沉浸式消费容器                  <- works_immersive_viewer_widget_test
///   - 交集归因埋点                    <- intersection_attribution_test
///   - 关注主体横滑                    <- following_subject_strip_test
///
/// gamma-local 数据现状（诚实标注，影响可在 App 内演示的范围）：
///   1) 推荐频道 feedQuery = {category: micro, identity: moment}（content-service 走
///      identity=moment 的 repository 分页 ListPublished 按 createdAt DESC 扫描，绕过
///      引擎）。已按 env-seed-first 向 gamma quwoquan_content 注入 24 条多形态 moment
///      （applier=quwoquan_service/scripts/seed/apply_content_moment_channel_seed.py，
///      fixture=contracts/metadata/_shared/test_fixtures/
///      content_recommendation_moment_channel.gamma_seed.json；全新非抑制作者 +
///      全新 id t4hrec_moment_* + 既有 archived-* 媒体 object key，createdAt 递减唯一
///      且置顶）。故「多形态卡片 + 连续下拉曝光不重复」现可在推荐频道 App 内真演示
///      （用例 home_rec_multiform_feed_paginates_without_repeat）；page1/page2 无重叠的
///      契约级证据见同目录 moment_feed_pagination_guest.json / _viewer.json。
///      现网 alpha_moment_* 作者已被 T3 负反馈加入 hidden_authors（预期生效非缺陷），
///      故仅靠旧种子推荐频道只回 1 条 fixture_moment_001——本轮新种子用未抑制作者绕开。
///   2) 个性化交集仅由 X-Client-User-Id 决定（auth-only=0 / 带 header=6/20）；
///      gamma-local 无 JWT 校验网关（T3 §1），App feed 读取按生产设计仅发送
///      Authorization（由生产网关注入身份），不在端侧硬塞 X-Client-User-Id，故
///      gamma-local 下交集行不渲染（环境/拓扑缺口）。新种子已在 tagRefs 写入含/不含
///      交集兴趣标签（含交集混合数据就位），但交集行渲染本身仍受该 X-Client-User-Id
///      环境缺口约束。本 T4 不改 lib 行为强制其渲染；交集渲染与 span 跳转由上述 T2
///      守护、数据就绪由 T3 证明，本 T4 用「作者头像→用户主页」覆盖对象跳转链路。
///
/// 执行方式（本地，emulator 访问宿主用 10.0.2.2）：
///   patrol test --target test/patrol/discovery/home_recommendation_journey_test.dart \
///     -d emulator-5554 \
///     --dart-define=APP_RUNTIME_ENV=gamma --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_T4_PATROL=true \
///     --dart-define=CLOUD_GATEWAY_BASE_URL=http://10.0.2.2:19000 \
///     --dart-define=API_CONTRACT_BASE_URL=http://10.0.2.2:19000 \
///     --dart-define=MEDIA_IMAGE_CDN_BASE_URL=http://10.0.2.2:19100 \
///     --dart-define=MEDIA_VIDEO_CDN_BASE_URL=http://10.0.2.2:19100 \
///     --dart-define=APP_CURRENT_USER_ID=us_01_3278_01kvevr8s7s3b0arr7x3p27efe \
///     --dart-define=TEST_AUTH_TOKEN=local-t4-token
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/constants/app_strings.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

// 首页推荐 feed 卡片容器 key（home_multi_form_feed.dart 真相源）。
const _kFeedCard0 = ValueKey<String>('home-feed-card-0');
const _kHomeSearchChrome = ValueKey<String>('home-search-chrome');
const _kRelationHeader = ValueKey<String>('home-relation-card-header');
const _kRelationActions = ValueKey<String>('home-relation-card-actions');

// 内容卡内容区点击目标（进入沉浸消费）：moment 网格 / 媒体 / 文章卡。
const _kContentTapKeys = <ValueKey<String>>[
  ValueKey<String>('home-moment-grid-tile-0'),
  ValueKey<String>('home-relation-card-media'),
  ValueKey<String>('home-article-card'),
];

// 进入用户主页后的可命中骨架 key。
const _kProfileKeys = <ValueKey<String>>[
  ValueKey<String>('profile-header-avatar'),
  ValueKey<String>('profile-shell-summary-card'),
];

void main() {
  // 注：用例声明顺序 = Patrol 执行顺序。负反馈用例改放在多形态深滚用例「之前」
  // （见该用例上方说明）：feed 已 seed 24+ 卡，负反馈本地移除单卡不再影响后续用例，
  // 而多形态用例的视频重压会反向令负反馈降级提示时序 flaky。
  patrolTest(
    'home_rec_feed_first_load_renders_real_remote_card',
    tags: ['t4', 'home-rec', 'discovery'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      assert(
        _apiContractEnv == 'gamma',
        'T4 home-rec journey must run with API_CONTRACT_ENV=gamma',
      );
      await _recoverToHomeFeed($);

      // 首刷：推荐 feed 必须渲染至少一张真实远端卡片（feed 非空）。
      expect(
        _existsInTree($, find.byKey(_kFeedCard0)),
        isTrue,
        reason: 'gamma 推荐 feed 首刷必须渲染至少一张卡片（feed 非空）',
      );
      // 卡片必须带真实远端社交 chrome（作者头部 + 互动操作行），证明这是一张
      // 多形态能力卡片承载真实远端数据，而非占位/空态。
      expect(
        _existsInTree($, find.byKey(_kRelationHeader)),
        isTrue,
        reason: '推荐卡片必须渲染作者头部（真实远端社交卡片）',
      );
      expect(
        _existsInTree($, find.byKey(_kRelationActions)),
        isTrue,
        reason: '推荐卡片必须渲染互动操作行（点赞/评论/分享/更多）',
      );
    },
  );

  // 负反馈用例放在多形态深滚用例「之前」：多形态用例会重度初始化多个视频播放器
  // （真机资源敏感），若先跑会令本用例点击「不感兴趣」后的降级提示 SnackBar 渲染
  // 时序退化而 flaky（实测：video 重压后本用例耗时 28~37s 且超时，未重压时 10s 通过）。
  // feed 已 seed 24+ 卡，负反馈本地移除单卡不再影响后续用例。
  patrolTest(
    'home_rec_negative_feedback_converges',
    tags: ['t4', 'home-rec', 'discovery'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      await _recoverToHomeFeed($);

      // 负反馈：更多 → 不感兴趣 → 即时收敛（卡片本地移除 + 降级提示 + 行为上报）。
      final openedMore = await _tapByKeyEnsureVisible(
        $,
        const ValueKey('home-feed-more-0'),
      );
      expect(openedMore, isTrue, reason: '应能点击首卡「更多」入口');
      await $.pump(const Duration(milliseconds: 400));

      final notInterested = $(find.text(AppStrings.notInterested));
      await notInterested.waitUntilVisible(timeout: const Duration(seconds: 6));
      await notInterested.tap();
      await $.pump(const Duration(milliseconds: 400));

      final converged = await _waitForFinderInTree(
        $,
        find.text(DiscoveryFeedText.feedNegativeFeedbackNotInterested),
        timeout: const Duration(seconds: 6),
      );
      expect(
        converged,
        isTrue,
        reason:
            '负反馈后应即时收敛：卡片本地移除并给出降级提示（行为同时上报 gamma，'
            '未来窗口收敛由 T3 真实 HTTP 证明）',
      );
    },
  );

  patrolTest(
    'home_rec_multiform_feed_paginates_without_repeat',
    tags: ['t4', 'home-rec', 'discovery'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      await _recoverToHomeFeed($);

      // env-seed-first 已向 gamma 注入 24 条多形态 moment 并置顶推荐频道（见文件头
      // 注释 1）。本用例在真机演示：① 首刷多形态非空 ② 连续下拉曝光不重复。

      // ① 首刷多形态非空：连续下拉前几屏内同时命中「moment 九宫格」与「视频卡」。
      final forms = await _collectFormsWhileScrolling($, maxDrags: 6);
      expect(
        forms.contains('moment-grid') && forms.contains('video'),
        isTrue,
        reason: '推荐频道首刷应渲染多形态（至少同时出现 moment 九宫格与视频卡）；'
            'forms=$forms',
      );

      // ② 连续下拉≥2 页 + 曝光不重复：持续下拉，累积不同视频 item 的 content id
      //    （home-video-player-<id> / home-video-focus-paused-<id> 含真实 id），
      //    并校验任意一帧内同一 item 不重复渲染（无单 item 连刷霸屏）。feed-card
      //    index = 数据索引（home_multi_form_feed 真相源），单调增长证明持续分页。
      final seenVideoIds = <String>{};
      var maxFeedCardIndex = -1;
      var perFrameDuplicateSeen = false;
      for (var i = 0; i < 16; i++) {
        final frameIds = _videoContentIdsInFrame($);
        if (frameIds.length != frameIds.toSet().length) {
          perFrameDuplicateSeen = true;
        }
        seenVideoIds.addAll(frameIds);
        maxFeedCardIndex = _maxFeedCardIndex($, fallback: maxFeedCardIndex);
        await _dragFeedDown($);
      }

      expect(
        perFrameDuplicateSeen,
        isFalse,
        reason: '连续下拉过程中同一 item 不得在同一帧重复渲染（无霸屏/重复曝光）',
      );
      expect(
        seenVideoIds.length >= 2,
        isTrue,
        reason: '连续下拉应曝光≥2 个不同视频形态 item（多形态 + 不重复）；'
            'seenVideoIds=$seenVideoIds',
      );
      expect(
        maxFeedCardIndex >= 8,
        isTrue,
        reason: '连续下拉应滚过多屏多卡（feed-card index 单调增长，证明持续分页）；'
            'maxFeedCardIndex=$maxFeedCardIndex',
      );

      // 用例间交接清理（Patrol 不在用例间重启 App）：回滚到 feed 顶部并多 pump
      // 几帧，让焦点视频暂停、释放播放资源，避免深滚 + 视频播放状态污染后续用例
      // （如负反馈用例的降级提示时序）。
      await _settleFeedToTopForHandoff($);
    },
  );

  patrolTest(
    'home_rec_open_immersive_consumption_and_return',
    tags: ['t4', 'home-rec', 'discovery'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      await _recoverToHomeFeed($);

      expect(
        $(_kHomeSearchChrome).visible,
        isTrue,
        reason: '进入沉浸前首页 chrome 应可见',
      );

      // 点击内容卡的内容区进入沉浸消费（图片/视频/文章 reader 统一入口）。
      final tapped = await _tapFirstContent($);
      expect(tapped, isTrue, reason: '应能点击到一张内容卡的内容区');
      await $.pump(const Duration(milliseconds: 400));
      await $.pump(const Duration(seconds: 1));

      // 进入沉浸：全屏沉浸路由覆盖首页，home chrome 不再可命中。
      final entered = await _waitUntil(
        () => !$(_kHomeSearchChrome).visible,
        timeout: const Duration(seconds: 15),
      );
      expect(
        entered,
        isTrue,
        reason: '点击内容卡应进入沉浸消费（首页 chrome 被全屏沉浸路由覆盖）',
      );

      // 返回：原生返回键应回到推荐 feed。
      await $.native.pressBack();
      await $.pump(const Duration(milliseconds: 400));
      await $.pump(const Duration(seconds: 1));
      final returned = await _waitUntil(
        () => $(_kHomeSearchChrome).visible,
        timeout: const Duration(seconds: 15),
      );
      expect(
        returned,
        isTrue,
        reason: '从沉浸消费返回后应回到推荐 feed',
      );
    },
  );

  patrolTest(
    'home_rec_author_object_nav_and_follow_entry',
    tags: ['t4', 'home-rec', 'discovery'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      await _recoverToHomeFeed($);

      // 对象跳转：点击作者头像进入其主页（与交集 name-span 同一目标；精确的
      // 「人名 span→主页 / 数字 span→交集列表」导航由 T2 home_intersection_object_nav
      // 守护）。
      final navigated = await _tapFirstAuthorAvatar($);
      expect(navigated, isTrue, reason: '应能点击到首卡作者头像');
      await $.pump(const Duration(milliseconds: 400));
      await $.pump(const Duration(seconds: 1));

      final reachedProfile = await _waitForAnyKeyInTree(
        $,
        _kProfileKeys,
        timeout: const Duration(seconds: 15),
      );
      expect(
        reachedProfile,
        isTrue,
        reason: '点击 feed 卡片作者应跳转到用户主页（对象跳转链路可达）',
      );

      // 可关注：主页/卡片提供「关注/已关注」语义入口。
      expect(
        _existsInTree($, find.text(UITextConstants.follow)) ||
            _existsInTree($, find.text(UITextConstants.following)),
        isTrue,
        reason: '主页/卡片应提供「关注/已关注」入口（可关注）',
      );

      await $.native.pressBack();
      await $.pump(const Duration(seconds: 1));
    },
  );
}

// ───────────────────────── helpers ─────────────────────────

bool _existsInTree(PatrolIntegrationTester $, Finder finder) =>
    finder.evaluate().isNotEmpty;

Future<bool> _waitForKeyInTree(
  PatrolIntegrationTester $,
  Key key, {
  required Duration timeout,
}) {
  return _waitForFinderInTree($, find.byKey(key), timeout: timeout);
}

Future<bool> _waitForAnyKeyInTree(
  PatrolIntegrationTester $,
  Iterable<Key> keys, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final key in keys) {
      if (find.byKey(key).evaluate().isNotEmpty) {
        return true;
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}

Future<bool> _waitForFinderInTree(
  PatrolIntegrationTester $,
  Finder finder, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}

Future<bool> _waitUntil(
  bool Function() predicate, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (predicate()) {
      return true;
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  return predicate();
}

/// Patrol 不在用例之间重启 App，需在每个用例开始时恢复到推荐 feed 干净态。
///
/// 关键安全约束：绝不在「首页壳层未就绪」时按返回键——在 Android 首页根 route
/// 上按返回会 finish Activity 直接退出 App、连带整个 instrumentation 崩溃。
/// 因此先等待首页壳层进入 widget 树，仅当首页活着但被子路由覆盖（chrome 在树
/// 但不可见）时才逐层弹回。
Future<void> _recoverToHomeFeed(PatrolIntegrationTester $) async {
  await _waitForKeyInTree(
    $,
    _kHomeSearchChrome,
    timeout: const Duration(seconds: 30),
  );
  await $.pump(const Duration(milliseconds: 500));

  for (var i = 0; i < 4; i++) {
    if ($(_kHomeSearchChrome).visible) {
      break;
    }
    if (!_existsInTree($, find.byKey(_kHomeSearchChrome))) {
      break;
    }
    await $.native.pressBack();
    await $.pump(const Duration(milliseconds: 600));
  }

  await _scrollFeedToTop($);
  await _waitForKeyInTree($, _kFeedCard0, timeout: const Duration(seconds: 60));
}

/// 推荐 feed 自身的垂直可滚动体（限定在 home-feed-recommend 子树内）。
Finder _feedScrollableFinder() {
  final scoped = find.descendant(
    of: find.byKey(const ValueKey('home-feed-recommend')),
    matching: find.byType(Scrollable),
  );
  if (scoped.evaluate().isNotEmpty) {
    return scoped;
  }
  return find.byKey(_kFeedCard0);
}

Future<void> _scrollFeedToTop(PatrolIntegrationTester $) async {
  for (var i = 0; i < 10; i++) {
    final scrollable = _feedScrollableFinder();
    if (scrollable.evaluate().isEmpty) {
      return;
    }
    if (_existsInTree($, find.byKey(_kFeedCard0))) {
      return;
    }
    await $.tester.drag(scrollable.first, const Offset(0, 700));
    await $.pump(const Duration(milliseconds: 300));
  }
}

Future<bool> _tapByKeyEnsureVisible(PatrolIntegrationTester $, Key key) async {
  final finder = find.byKey(key);
  if (finder.evaluate().isEmpty) {
    return false;
  }
  try {
    await $.tester.ensureVisible(finder.first);
    await $.pump(const Duration(milliseconds: 200));
  } catch (_) {
    // ensureVisible 在无 Scrollable 祖先时会抛出；直接尝试点击当前位置。
  }
  await $.tester.tap(finder.first);
  await $.pump(const Duration(milliseconds: 300));
  return true;
}

String? _valueKeyString(Element e) {
  final k = e.widget.key;
  return k is ValueKey<String> ? k.value : null;
}

/// 当前 widget 树中每张视频卡承载的 content id。每张视频卡在 videoUrl 非空时
/// 恰好挂载一个 `home-video-player-{id}`（无条件渲染，见
/// home_multi_form_feed_media_grid.dart），故同一帧内同一 id 出现多次即表示同一
/// item 被重复渲染在多个位置（霸屏/重复曝光）。这里只采集 player key：占位
/// `home-video-focus-paused-{id}` 与 player 是同一张卡的兄弟节点、承载相同 id，
/// 并入会造成「同帧自重复」的假阳性。
List<String> _videoContentIdsInFrame(PatrolIntegrationTester $) {
  const playerPrefix = 'home-video-player-';
  final ids = <String>[];
  final finder = find.byWidgetPredicate((w) {
    final k = w.key;
    return k is ValueKey<String> && k.value.startsWith(playerPrefix);
  });
  for (final e in finder.evaluate()) {
    final v = _valueKeyString(e);
    if (v == null) {
      continue;
    }
    final id = v.substring(playerPrefix.length);
    if (id.isNotEmpty) {
      ids.add(id);
    }
  }
  return ids;
}

/// 当前可命中的最大 feed-card 数据索引（`home-feed-card-{index}`）。
int _maxFeedCardIndex(PatrolIntegrationTester $, {required int fallback}) {
  const prefix = 'home-feed-card-';
  var maxIdx = fallback;
  final finder = find.byWidgetPredicate((w) {
    final k = w.key;
    return k is ValueKey<String> && k.value.startsWith(prefix);
  });
  for (final e in finder.evaluate()) {
    final v = _valueKeyString(e);
    if (v == null) {
      continue;
    }
    final idx = int.tryParse(v.substring(prefix.length));
    if (idx != null && idx > maxIdx) {
      maxIdx = idx;
    }
  }
  return maxIdx;
}

Future<void> _dragFeedDown(PatrolIntegrationTester $) async {
  final scrollable = _feedScrollableFinder();
  if (scrollable.evaluate().isEmpty) {
    return;
  }
  await $.tester.drag(scrollable.first, const Offset(0, -500));
  await $.pump(const Duration(milliseconds: 350));
}

/// 用例退出前的交接清理：强力回滚到推荐 feed 顶部（card-0 可见即停），并多
/// pump 数帧让焦点视频暂停、释放播放资源，避免深滚 + 视频播放状态污染后续用例。
Future<void> _settleFeedToTopForHandoff(PatrolIntegrationTester $) async {
  for (var i = 0; i < 24; i++) {
    if (_existsInTree($, find.byKey(_kFeedCard0))) {
      break;
    }
    final scrollable = _feedScrollableFinder();
    if (scrollable.evaluate().isEmpty) {
      break;
    }
    await $.tester.drag(scrollable.first, const Offset(0, 900));
    await $.pump(const Duration(milliseconds: 250));
  }
  await $.pump(const Duration(seconds: 1));
}

/// 连续下拉前几屏，收集出现过的形态标识（moment-grid / carousel / video）。
Future<Set<String>> _collectFormsWhileScrolling(
  PatrolIntegrationTester $, {
  required int maxDrags,
}) async {
  final forms = <String>{};
  for (var i = 0; i <= maxDrags; i++) {
    if (_existsInTree($, find.byKey(const ValueKey('home-moment-grid')))) {
      forms.add('moment-grid');
    }
    if (_existsInTree(
      $,
      find.byKey(const ValueKey('home-image-carousel-dots')),
    )) {
      forms.add('carousel');
    }
    if (_existsInTree(
      $,
      find.byKey(const ValueKey('home-image-carousel-counter')),
    )) {
      forms.add('carousel-counter');
    }
    if (_videoContentIdsInFrame($).isNotEmpty) {
      forms.add('video');
    }
    if (forms.contains('moment-grid') && forms.contains('video')) {
      break;
    }
    await _dragFeedDown($);
  }
  return forms;
}

Future<bool> _tapFirstContent(PatrolIntegrationTester $) async {
  for (final key in _kContentTapKeys) {
    if (await _tapByKeyEnsureVisible($, key)) {
      return true;
    }
  }
  return _tapByKeyEnsureVisible($, _kFeedCard0);
}

Future<bool> _tapFirstAuthorAvatar(PatrolIntegrationTester $) async {
  final header = find.byKey(_kRelationHeader);
  if (header.evaluate().isEmpty) {
    return false;
  }
  final avatar = find.descendant(
    of: header.first,
    matching: find.byType(CupertinoButton),
  );
  if (avatar.evaluate().isEmpty) {
    return false;
  }
  try {
    await $.tester.ensureVisible(avatar.first);
    await $.pump(const Duration(milliseconds: 200));
  } catch (_) {}
  await $.tester.tap(avatar.first);
  await $.pump(const Duration(milliseconds: 300));
  return true;
}
