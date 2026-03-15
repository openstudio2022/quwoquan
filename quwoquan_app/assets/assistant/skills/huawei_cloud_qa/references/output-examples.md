# 输出示例

## 标准输出 — L1 售前（产品定价）

### 机器轨
```json
{
  "contractVersion": "assistant_turn",
  "decision": {"nextAction": "answer"},
  "slotState": {
    "product": {"value": "盘古大模型", "source": "user_query"},
    "phase": {"value": "presale", "source": "inferred"},
    "level": {"value": "L1", "source": "classified"},
    "subtype": {"value": "entity", "source": "classified"}
  },
  "toolPlan": [],
  "askUser": {"slotId": "", "prompt": "", "required": false, "suggestions": []},
  "userMarkdown": "（见下方 Markdown）"
}
```

### 用户轨
```markdown
## 💰 盘古大模型 — 定价概览

**计费模式**：按 Token 计费（输入 Token + 输出 Token 分别计价）

### 主要模型定价

| 模型 | 输入价格 | 输出价格 | 适用场景 |
|------|----------|----------|----------|
| 盘古 NLP 大模型 | ¥X.XX / 千Token | ¥X.XX / 千Token | 文本理解、生成 |
| 盘古 CV 大模型 | 按调用次数 | — | 图像识别、生成 |
| 盘古行业大模型 | 按部署规模 | — | 行业定制 |

### 计费方式
- **按需调用**：无最低消费，用多少付多少
- **资源包**：预购 Token 包享折扣
- **私有化部署**：按算力规模定价，需联系售前

> 📎 参考：[盘古大模型定价](https://www.huaweicloud.com/pricing.html#/pangu)。以华为云控制台实时价格为准。

---
💬 **你可能还想了解**
- 盘古和千问/文心一言的定价对比？
- 如何申请盘古大模型试用？
- ModelArts 训练任务怎么计费？
```

## 标准输出 — L2d 售后（故障诊断）

### 用户轨
```markdown
## 🔍 ECS 无法 SSH 连接 — 诊断与修复

### 现象确认
尝试 SSH 连接 ECS 实例时返回 "Connection refused" 或连接超时。

### 可能原因与排查

| # | 可能原因 | 排查方法 | 修复操作 |
|---|----------|----------|----------|
| 1 | 安全组未放行 22 端口 | 控制台 → 安全组 → 入方向规则，检查是否有 TCP/22 | 添加入方向规则：协议 TCP，端口 22，源 0.0.0.0/0 |
| 2 | ECS 未绑定 EIP | 控制台 → ECS → 网络信息，检查是否有弹性公网 IP | 绑定 EIP 或使用 VPC 内网跳板机 |
| 3 | sshd 服务未启动 | VNC 登录后执行 `systemctl status sshd` | `systemctl start sshd && systemctl enable sshd` |
| 4 | 防火墙规则阻止 | VNC 登录后执行 `iptables -L -n` 或 `firewall-cmd --list-all` | 放行 22 端口或临时关闭防火墙排查 |
| 5 | 密钥对不匹配 | 检查本地 `~/.ssh/` 下的密钥是否对应该实例 | 重置密码或重新注入密钥对 |

### 快速修复命令
```bash
# VNC 登录后执行
systemctl start sshd
firewall-cmd --add-port=22/tcp --permanent
firewall-cmd --reload
```

### 若仍未解决
1. 提交工单：[华为云工单系统](https://console.huaweicloud.com/ticket/)，附带实例 ID 与报错截图
2. 电话支持：拨打 **950808 转 1**（技术支持）
3. 社区求助：[华为云社区](https://bbs.huaweicloud.com/)

> 📎 参考：[ECS SSH 连接故障排查](https://support.huaweicloud.com/ecs_faq/ecs_faq_0521.html)
```

## 标准输出 — L2c 竞品对比

### 用户轨
```markdown
## 📊 华为云 vs 阿里云 — 大模型服务对比

### 对比矩阵

| 维度 | 华为云（盘古/ModelArts） | 阿里云（通义千问/PAI） |
|------|--------------------------|------------------------|
| 基础大模型 | 盘古系列（NLP/CV/多模态/行业） | 通义千问系列（Qwen） |
| 开发平台 | ModelArts（全流程 AI 开发） | PAI（机器学习平台） |
| 模型即服务 | MaaS（API 调用） | 百炼（API 调用） |
| 算力底座 | 昇腾 NPU（自研） | GPU（NVIDIA） |
| 行业大模型 | 矿山、气象、药物等行业大模型 | 金融、法律、医疗等行业模型 |
| 私有化部署 | 支持（昇腾 + 鲲鹏） | 支持（GPU） |
| 合规优势 | 国产全栈（芯片→框架→模型） | 依赖 NVIDIA GPU |

### 华为云差异化优势
- **全栈自主**：从昇腾芯片到 CANN 算子库到 MindSpore 框架到盘古模型，全链路国产可控
- **行业深耕**：盘古行业大模型覆盖矿山、气象、药物发现等垂直场景
- **政企信赖**：在政务、金融、能源等对安全合规要求高的行业积累深厚

### 阿里云优势
- **开源生态**：通义千问系列开源，社区活跃
- **电商场景**：与阿里电商生态深度融合
- **全球覆盖**：海外节点丰富

### 选型建议
若看重国产自主可控、行业定制与政企合规 → 华为云；若看重开源生态与电商场景 → 阿里云。建议根据实际业务需求进一步评估。

> ⚖️ 各厂商信息基于公开资料整理，具体以各厂商官方最新发布为准。
```

## 降级输出（检索失败）

### 用户轨
```markdown
## ☁️ 华为云 XX 产品 — 信息有限

基于当前可获取的信息，为您整理如下内容：

{基于模型训练知识的回答}

以上信息可能不是最新版本，建议在以下渠道确认：
> - [华为云官网文档](https://support.huaweicloud.com/)
> - 拨打 **950808 转 1**（技术支持）
> - 提交[工单](https://console.huaweicloud.com/ticket/)获取精确信息

---
💬 **你可能还想了解**
- {相关产品/服务推荐}
- {替代方案建议}
```
