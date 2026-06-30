# 阶段证据：base-aware wordCount + 去 baseDraftText 截断（修 baseDraftFidelity 数学不可达根因）

## 根因（P5 都江堰多目的地文章 fidelity 17.7% 复发）

1. **baseDraftText 截断**：`route_compose._attach_base_draft_text` 把注入 prompt 的底稿正文
   截到 `[:4000]`，而整篇底稿 ~8900 字。agent 只看到半篇，看不到的内容无法保留，
   `baseDraftFidelity`（按整篇底稿三连重叠判）必然偏低。
2. **wordCount 固定上限**：light-edit 文章字数目标固定 max≈1600，远小于底稿清洗长度。
   成稿被迫把 ~8900 字压成 ~1600 字时，三连覆盖率数学上最多 ~18%，与 `>=55%` 硬门互斥。

## 修复

- `_common/base_draft.py`：
  - 新增 `BASE_DRAFT_PROMPT_MAX_CHARS = 24000`（仅对书籍级超长底稿设安全上限）。
  - 新增 `clean_base_draft_length(base_text)`：去平台噪声后的可读正文字数。
  - 新增 `base_aware_word_count(base_text, carrier, source_use_mode)`：
    light-edit 文章字数目标 = `[max(下限, 0.62*clean), 1.12*clean]`；
    image/gallery 与非改编源返回 None（短配文/不可改编不设底稿字数门）。
- `produce/route_compose.py::_attach_base_draft_text`：
  - `baseDraftText` 截断改为 `[:BASE_DRAFT_PROMPT_MAX_CHARS]`（整篇注入）。
  - 调 `base_aware_word_count` 设 `writing_pack.wordCount`（随底稿长度）。

## 验证

- 新单测 `test_base_aware_word_count_tracks_long_base_draft` PASS（3 passed）：
  长底稿 max>1600 且 >= clean_len，min>=0.55*clean（数学可行），image/blocked/短底稿返回 None。
- 集成（重跑 compose-brief，都江堰多目的地文章）：
  - `wordCount = {min: 3736, max: 6749}`（不再固定 1600）
  - `baseDraftText len = 6331`（不再截断到 4000）
  - prompt `字数区间: 3736–6749 字（去空白）`
  - `clean_base_len ≈ 6026`，`min 3736 >= 0.55*6026=3314` → fidelity>=55% 数学可达。

## 影响面

- 仅作用于 light-edit（可改编源）文章；entity 主页三件套、image/gallery 配文不受影响。
- 修复后 prompt 字数区间与 fidelity 门不再互斥，为 P5 bounded 复跑提供数学可行前提。
