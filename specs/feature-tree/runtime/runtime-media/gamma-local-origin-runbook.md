# gamma 本地公网回源 Runbook

## 目标

在正式 CDN / 对象存储尚未就绪前，让 `gamma-pre` 继续使用 ECS 侧统一媒体域名，但实际由本机媒体服务通过公网地址 / tunnel 作为临时 origin 回源。

## 适用边界

- 仅用于 `gamma-pre` 手工联调、T3/T4 验证。
- 不用于长期无人值守 CI。
- 不作为正式商用架构。

## 本机步骤

1. 启动本机媒体 origin：

```bash
scripts/start_gamma_local_media_origin.sh \
  --bind 0.0.0.0 \
  --port 18098 \
  --public-base-url "https://<your-tunnel-domain>"
```

如果你想直接使用“本机当前公网 IP + 端口”，可改用：

```bash
scripts/start_public_ip_media_origin.sh \
  --bind 0.0.0.0 \
  --port 18200 \
  --public-port 18200
```

它会在本机动态解析这一次的公网 IP，并生成：

```text
http://<current-public-ip>:18200
```

注意：这一步只负责“解析当前公网 IP 并启动本地服务”，并不保证运营商 / 路由 / 热点真的允许外网入站。

2. 确保 tunnel / 公网域名能把 `https://<your-tunnel-domain>/media/...` 转到该本机端口。

3. 本机抽样验证：

```bash
curl -I "https://<your-tunnel-domain>/media/avatar/user/fixture_user_current/v1/avatar.png"
curl -I "https://<your-tunnel-domain>/media/image/post/fixture_photo_001/v1/cover.png"
```

若是“公网 IP 直连模式”，可额外从公网侧检查端口是否真的打开：

```bash
python3 scripts/check_public_ip_open_port.py --port 18200
```

## ECS 部署步骤

设置以下环境变量后执行：

```bash
export GAMMA_ECS_MEDIA_ORIGIN_BASE_URL="https://<your-tunnel-domain>"
export MEDIA_AVATAR_CDN_BASE_URL="http://<ecs-public-host>:18000"
scripts/deploy_gamma_ecs.sh
```

说明：

- `MEDIA_AVATAR_CDN_BASE_URL` 是 App / 服务对外看到的稳定媒体基址。
- `GAMMA_ECS_MEDIA_ORIGIN_BASE_URL` 是 ECS `gamma-proxy` 实际回源的本机公网地址。

## 预期行为

- ECS 对外仍然暴露自己的 `gamma-avatar / gamma-image / gamma-video` 域名或统一网关入口。
- `gamma-proxy` 的 `/media/*` 与独立媒体 host 回源到 `GAMMA_ECS_MEDIA_ORIGIN_BASE_URL`。
- `scripts/deploy_gamma_ecs.sh` 不再上传 `test_fixtures/media` 与 `original_media` 整库。

## 风险

- 本机睡眠、断网、切换网络会导致 gamma 图片不可用。
- tunnel 稳定性直接影响图片加载时延。
- 本机上传带宽会成为远端回源瓶颈。

## 回滚

1. 清空 `GAMMA_ECS_MEDIA_ORIGIN_BASE_URL`
2. 改用云侧共享盘 / 对象存储 / 本地 `/srv/media`
3. 重新执行 `scripts/deploy_gamma_ecs.sh`
