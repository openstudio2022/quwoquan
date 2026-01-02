# 趣我圈 (QuWoQuan) 项目

趣我圈是一个社交内容应用项目，包含多个子模块。

## 项目结构

```
quwoquan/
├── quwoquan_app/          # Flutter 移动应用（子模块）
├── quwoquan_service/      # 后端服务（待开发）
└── social_content_app/    # 社交内容应用（待迁移）
```

## 子模块

### quwoquan_app
Flutter 移动应用，使用 Riverpod 进行状态管理。

## 开发指南

### 初始化子模块

如果是首次克隆此仓库，需要初始化子模块：

```bash
git submodule update --init --recursive
```

### 更新子模块

```bash
git submodule update --remote
```

### 在子模块中工作

```bash
cd quwoquan_app
# 进行开发工作
git add .
git commit -m "Your commit message"
git push
```

然后回到主仓库提交子模块的更新：

```bash
cd ..
git add quwoquan_app
git commit -m "Update quwoquan_app submodule"
git push
```

## Git 配置

本项目使用 SSH 密钥进行 GitHub 认证。SSH 密钥已配置在 `~/.ssh/id_ed25519_quwoquan`。

## 贡献指南

1. 在主仓库创建功能分支
2. 在相应的子模块中进行开发
3. 提交子模块更改
4. 在主仓库中更新子模块引用
5. 提交并推送主仓库更改

