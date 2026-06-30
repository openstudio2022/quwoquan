# 阶段证据 C2：P5 agent 文章创作完成

## 命令（bound 840s，max-workers=1，--until produce_author 有界）
```
PATH=$HOME/.local/bin:$PATH  CURSOR_API_KEY=<QWQ_CURSOR_API_KEY_FILE>
timeout 840 ./quwoquan_data/.venv/bin/python quwoquan_data/scripts/cli.py \
  data workflow run --task '旅行/地域/四川省/景区/创作冒烟试跑' --batch p5_sichuan_20260630 \
  --managed --resume --runtime local --model composer-2.5 --agent-provider cursor_sdk \
  --max-workers 1 --until produce_author
```

## 结果
- 用时 ~754s（含 bridge 预热 + 8 篇顺序创作），exit 0。
- `✓ produce_author (checkpoint): 文章/主页正文已由 Agent 创作，图片作品采用结构化证据包`
- `stopped at --until produce_author`（有界停止，未越界跑 review/materialize）。
- 8 篇文章 `draft_meta.generator` 终态：**8 agent / 0 pending**。
  - 九寨沟 ×3、峨眉山 ×2、都江堰 ×3。
- 6 个图片画报不进 produce_author（走结构化证据包），符合三类解耦。

## 抗超时纪律生效
- 草稿逐 ref 落盘到沙箱 runtime（generator 由 pending→agent 增量推进，监控可见 2→6→7→8），
  即使会话断连，已创作草稿持久，`--resume` 跳过已完成 ref。
- 单次 managed 运行 bound 840s；composer-2.5 真实创作 ~70s/篇，无单次 agent 调用超 15min。

## 下一步 C3
`--managed --resume` 驱动 produce_annotate → produce_review（确定性门）→ materialize → ship，
ReAct 有界（2）+ allowPartialContent 收口；逐项门禁与 firstPassRate。
