# Clash 中让 Cursor 走代理的规则配置

参考 [Clash 规则说明](https://github.com/Dreamacro/clash/wiki/configuration#rule)：
规则按**从上到下**匹配，**第一条命中即生效**。若希望 Cursor 相关域名走代理而非直连，需要把 Cursor 的规则写在「直连兜底」规则（如 `GEOIP,CN,DIRECT` 或 `MATCH,DIRECT`）**之前**。

## Cursor 相关域名

- `cursor.com`（主站、文档、仪表盘）
- `api.cursor.com`（API、AI、认证等）

使用 `DOMAIN-SUFFIX,cursor.com` 可同时匹配 `cursor.com`、`api.cursor.com`、`www.cursor.com`、`docs.cursor.com` 等所有子域。

## 在 config.yaml 的 rules 里添加（走代理）

把下面几行**插入到你当前 `rules:` 列表的靠前位置**（在 `GEOIP,CN,DIRECT`、`MATCH,DIRECT` 等兜底规则之前）：

```yaml
rules:
  # ---------- Cursor 走代理（勿放直连兜底之后）----------
  - DOMAIN-SUFFIX,cursor.com,Proxy
  # ---------- 以下为你原有规则，例如 ----------
  # - GEOIP,CN,DIRECT
  # - MATCH,Proxy
```

说明：

- 将上面的 `Proxy` 改成你 Clash 里实际使用的**代理策略组名称**（如 `🚀 节点选择`、`PROXY`、`proxy` 等）。
- 若希望 Cursor 走某个固定节点，可先建一个只包含该节点的策略组，再把上面规则里的 `Proxy` 换成该策略组名。

## 示例：完整 rules 顺序示意

```yaml
rules:
  - DOMAIN-SUFFIX,cursor.com,Proxy
  - DOMAIN-SUFFIX,openai.com,Proxy
  - GEOIP,CN,DIRECT
  - MATCH,Proxy
```

这样 Cursor 与 OpenAI 会走代理，国内 IP 直连，其余走代理。

## 修改后

1. 保存 Clash 的 `config.yaml`（或你使用的配置文件名）。
2. 在 Clash / ClashX / ClashX Pro 中重新加载配置或重启核心。
3. 在 Cursor 里测试网络（例如请求 AI 或打开账号）。

若仍直连，检查是否有其它规则先命中了 Cursor 的域名（例如某条 `DOMAIN-KEYWORD,xxx,DIRECT`），或策略组名称是否写错。
