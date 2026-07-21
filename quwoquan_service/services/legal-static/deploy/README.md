# legal-static 发布单元

`legal-static` 是法律与隐私合规文档的独立静态资源发布单元，不归属任何业务领域服务，也不随内容页、App 包或服务镜像一起打包。

## 目录与 URL

- 源文件：`quwoquan_service/services/legal-static/source/manifest.yaml` 与 `quwoquan_service/services/legal-static/source/versions/<version>/<document>.html`
- 包输出：`QWQ_DEPLOY_WORK_ROOT/<target>/packages/legal-static/<version>/`
- 稳定入口：`/legal/user-agreement`、`/legal/privacy-policy`、`/legal/permissions`、`/legal/third-party-sdk-list`
- 版本入口：`/legal/<version>/<document>`
- prod canonical：`https://quwoquan.com/legal/*`

发布包会生成 `public/legal/...` 静态目录、`manifest.json`、`checksums.json`、`release_metadata.json`，并刷新 `QWQ_DEPLOY_WORK_ROOT/<target>/packages/legal-static/current` 指针。gateway/CDN 只挂载 `current/public`，不读取业务服务镜像。

## 命令

```bash
python3 quwoquan_ops/cli/stackctl.py package --env gamma --kind legal-static
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind legal-static
python3 quwoquan_ops/cli/stackctl.py package --env prod --kind legal-static
python3 quwoquan_ops/cli/stackctl.py verify --env prod --kind legal-static
```

prod 发布前必须先完成 gamma legal-static 包校验与 URL 探测。当前 `2026-07` 免费社区版本已补齐协议、隐私、权限与 SDK 披露口径，但主体、备案、客服电话等仍须法务与运营补齐；prod 包会按 `prodPlaceholderPolicy: deny` 阻断，直到正式主体信息完整。

## App / Service 边界

App 只消费 URL 与版本号：

- `APP_LEGAL_BASE_URL`
- `APP_USER_AGREEMENT_URL`
- `APP_PRIVACY_POLICY_URL`
- `APP_USER_AGREEMENT_VERSION`
- `APP_PRIVACY_POLICY_VERSION`

user-service 只校验并保存登录同意版本，正文不进入 user-service。后续新增付费、会员、广告、电商、退款/发票、自动续费等协议时，必须先追加 manifest 文档，再补 App/页面入口，并关闭 backlog 中的商业化条款待办。
