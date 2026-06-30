# RC3 子步 A：内联 `<img>` src 捕获 + 同源清单导出（抽取器层）

阶段：fix-rc3-inline-img（最关键）— 子步 A（离线 / hermetic，无网络）

## 背景（九寨沟底稿审视结论）

底稿 `https://touch.travel.qunar.com/youji/7870084` 是**以图为主、图文混排**的游记，但落盘的
`source.md` 内联图严重缺失、图片对不上。根因定位：

- `_InlineFigureHTMLTextExtractor` 已在内联 `<img>` 位置就地输出 `:::figure ![cap](asset://source-inline-NNN)`
  占位符（保留图文交错），**但丢弃了 `<img src>` URL**。
- 占位符无法关联真实图片 URL ⇒ 内联图无法就地下载、`sourceAssetRef` 无法锚定 ⇒ 图文分离、图缺失。

## 本子步改动（`quwoquan_data/scripts/download/fetch.py`）

1. `_InlineFigureHTMLTextExtractor`：
   - 新增 `base_url` 构造参数与 `_inline_images` 清单。
   - `_usable_img_src()`：只放行可就地下载的 src（http/https/协议相对/相对路径）；
     `data:`/`javascript:`/`about:`/纯锚点 `#`/空一律视为不可下载，**不再产生悬空占位**
     （消除"图文对不上"的悬空 asset://）。
   - 捕获每个可下载 `<img>` 的 `{placeholderId, src(绝对), rawSrc, caption}`，src 经
     `urljoin(base_url, src)` 解析为绝对 URL；`figure_index` 仅对可下载图自增，保证
     清单与正文占位 **1:1 同序对齐**。
   - 新增 `inline_images()` 读取清单。
2. `_html_to_plain_text(html, base_url="")` 改为薄壳，委托新
   `_html_to_plain_text_with_inline_images(html, base_url) -> (text, inline_images)`；
   既有单参调用全部兼容。
3. `_qunar_html_plaintext` 传入 `base_url=url`；新增 `_qunar_html_with_inline_images`。
4. 新增公共 `extract_page_text_with_inline_images(html_bytes, url, *, extractor)`：
   - `qunar_html`/`generic_html`：返回 `(正文, 内联图清单)`，正文与 `extract_page_text` 一致。
   - 其它 extractor（`wikipedia_api` 走 API assets；baike/official 非图文混排游记）：
     返回 `(正文, [])`，**不引入跨源/二次网络的第二图源**（守 1:1 同源）。

## 测试证据（local_contract，hermetic）

`quwoquan_data/tests/download/test_fetch_registry_dispatch.py` 新增 4 例：

- `test_inline_images_capture_src_and_align_with_placeholders`：src 捕获、清单与
  `source-inline-NNN` 占位同序、caption 对齐、正文与 `extract_page_text` 一致。
- `test_inline_images_skip_data_uri_and_empty_src`：data:/空 src 不产占位也不进清单，真实图仍按序。
- `test_inline_images_resolve_relative_src_against_page_url`：相对 src 按页面 URL 解析为绝对。
- `test_non_html_extractor_returns_no_inline_images`：wikipedia_api 内联清单为空。

`python3 quwoquan_data/tests/download/test_fetch_registry_dispatch.py` → 18 passed（14 旧 + 4 新）。

## 后续子步（同一 RC3）

- 子步 B：`fetch_source_payload` 对 qunar/generic 返回 `inlineImages`（绝对 URL）。
- 子步 C：`write_source_unit` 就地同源下载内联图，把 `asset://source-inline-NNN` 占位
  重写为下载后真实 `sourceAssetId`，失败的图降级（去占位/text_only），完成段落锚定。
- 子步 D：来源单元层就地下载 + sourceRef 锁本源 + 锚定的契约测试。
- 接入 `verify_quwoquan_data.sh`。
