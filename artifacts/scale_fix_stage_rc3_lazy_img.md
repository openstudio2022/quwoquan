# RC3 收口:lazy-load 内联图就地同源抽取修复

## 背景(用户实测漏图根因)

用户审视九寨沟游记底稿(去哪儿移动页 `touch.travel.qunar.com/youji/*`)发现:底稿应有数十张图,
但 `source.md` 图片严重缺失、对不上。定位为 RC3 内联图抽取缺陷,而非下载/门禁问题。

## 根因

去哪儿等 lazy-load 站点把**真实图地址放进 `data-original` / `data-src`**,`<img src>` 仅留
1px/loading 占位 gif(如 `blank.gif`)。原 `_InlineFigureHTMLTextExtractor` 先取 `src`,命中占位即
返回,真实 `data-*` 永不被消费 → 游记数十张正文图被占位吞掉。

缓存页实测(`su_c0b0e69bf3c8f4a51ad9/page.html`):1502 个 `<img>`,其中约 1489 个走 lazy 属性。

## 修复(quwoquan_data/scripts/download/fetch.py)

`_InlineFigureHTMLTextExtractor`:

1. 新增 `_resolve_img_src(attr)`:**优先 lazy data-\* 真实地址**
   (`data-original`/`data-actualsrc`/`data-src`/`data-lazy-src`/`data-lazy`/`data-echo`),无 lazy 才退回 `src`。
2. `_usable_img_src` 新增占位/装饰图过滤(`blank|spacer|placeholder|loading|grey|transparent|pixel|1x1|s.gif|t.gif|default` 等 gif/png/svg),
   占位图不作为正文配图。
3. 仍兼容仅有 `src` 的普通 `<img>`(头像、测试样本)→ 原行为不变。

## 验证证据(离线,缓存页直测)

- 缓存 page.html 抽取:**content-like=1495 / avatar-chrome=7**(修复前真实游记图被占位吞掉)。
  真实图来自 `tr-osdcp.qunarzz.com/tr_osd_tr_hy/...`(去哪儿游记 CDN),占位 gif 全部被滤除。
- 契约测试(全绿):
  - `tests/download/test_fetch_registry_dispatch.py`(19)
  - `tests/local_contract/download/test_inline_source_images__local_contract_test.py`(4,含新增
    `test_inline_extractor_prefers_lazy_data_attr_over_placeholder_src`)
  - `tests/common/test_source_unit_evidence_chain.py`(5)

## 锚定(防回退)

新增 `test_inline_extractor_prefers_lazy_data_attr_over_placeholder_src`:断言 lazy `data-original`/`data-src`
真实地址被抽出、占位 `blank.gif`/`loading.gif` 绝不入选、普通 `src` 图仍保留。

## 仍待办(本轮后续)

- 内容相关性:发现层对部分实体返回了不相关游记 / 搜索结果页(记为 finding,非本修复范围)。
- P5 四川三类 scaled-e2e:download 阶段已验证(实体百科择优 + su_* 布局),authoring 阶段
  `produce_compose` 命中 ReAct 回退上限,需 bound 单次 agent 调用断点续跑。
