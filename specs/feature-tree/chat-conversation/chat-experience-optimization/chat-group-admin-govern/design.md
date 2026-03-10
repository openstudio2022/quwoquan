# chat-group-admin-govern 设计方案

## 设计动因

群聊缺少管理员治理体系：无群管理页、无群主转让、无管理员设置、群名称和隐私屏障无权限控制。需要建立群主+最多 3 管理员的分级治理闭环。

## 上游输入评审

- `chat-group-admin-govern/spec.md` 已冻结 GA1~GA10 功能
- `acceptance.yaml` 已定义 A1~A11 验收
- `group-settings/spec.md` 已冻结群设置页边界（退出群聊为唯一危险操作）
- 本特性在现有群设置页基础上新增"群管理"入口和权限控制

## 方案对比

### 对比 1：群管理入口位置

#### 方案 A：群设置页内嵌展开区

**优点**：不新增页面
**缺点**：群设置页职责膨胀，违反 `group-settings` 冻结的边界

#### 方案 B：独立群管理页（选定）

**优点**：职责分离，群设置页保持轻量，管理员专属入口
**缺点**：多一个页面

**选定方案 B**：与微信一致，独立群管理页，从群设置页新增入口行跳转。

### 对比 2：管理员存储

#### 方案 A：ConversationMember.role 字段（选定）

利用已有的 `role` 字段（`owner` / `admin` / `member`），无需新建字段。

**优点**：复用现有数据模型
**缺点**：需要 `PUT /admins` 接口批量更新 role

#### 方案 B：独立 admins 数组

**优点**：查询方便
**缺点**：与 member 列表冗余

**选定方案 A**：复用 `ConversationMember.role`。

### 对比 3：群主转让确认弹窗

单一方案：`CupertinoAlertDialog` 居中弹窗，与微信一致。

## 关键设计决策

### KD-1：ConversationGroupSettings DTO 扩展

```dart
class ConversationGroupSettings {
  final bool qrCodeJoinEnabled;
  final bool joinRequiresApproval;
  final bool nameEditableByAdminOnly;
  final bool privacyShieldAdminOnly;
  
  factory ConversationGroupSettings.fromMap(Map<String, dynamic> map);
  Map<String, dynamic> toMap();
}
```

### KD-2：GroupManagePage 设计

```dart
class GroupManagePage extends ConsumerStatefulWidget {
  final String conversationId;
}
```

页面结构：
```
区块 1：二维码进群 [Switch]
区块 2：进群需确认 [Switch] + 仅管理员改群名 [Switch]
区块 3：群主转让 [>] + 群管理员 [>]（仅群主可见）
区块 4：解散该群聊 [红色文字]（仅群主可见）
```

### KD-3：TransferOwnershipPage 设计

```dart
class TransferOwnershipPage extends ConsumerStatefulWidget {
  final String conversationId;
}
```

- 成员列表（排除自己），支持搜索和字母索引
- 选中成员后弹出 `CupertinoAlertDialog`（屏幕居中）
- 确认文案："确定选择 {name} 为新群主，你将自动放弃群主身份。"
- 确认后调用 `PATCH /conversations/{id}/owner`
- 成功后 pop 回群设置页，角色已更新

### KD-4：GroupAdminsPage 设计

```dart
class GroupAdminsPage extends ConsumerStatefulWidget {
  final String conversationId;
}
```

- 多选列表，排除群主
- 已选成员缩略头像显示在顶部搜索栏左侧
- 最多选 3 人，超出时 `showCupertinoDialog` 提示"最多选择 3 位管理员"
- 右上角"完成(N)"按钮
- 确认后调用 `PUT /conversations/{id}/admins`

### KD-5：权限拦截设计

#### 群名称权限

```dart
void _onGroupNameTap() {
  if (groupSettings.nameEditableByAdminOnly && !isAdminOrOwner) {
    showCupertinoDialog(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        content: Text('群组已设定为只有群主或管理员才能修改群名'),
        actions: [CupertinoDialogAction(child: Text('确定'), onPressed: () => Navigator.pop(context))],
      ),
    );
    return;
  }
  // 正常编辑流程
}
```

#### 隐私屏障权限

```dart
Switch(
  value: _privacyShield,
  onChanged: isAdminOrOwner ? (v) => setState(() => _privacyShield = v) : null,
  // onChanged: null → Switch 自动 disabled 灰色状态
)
```

### KD-6：ChatRepository 新增方法

```dart
abstract class ChatRepository {
  // 已有方法...
  
  // 新增
  Future<Map<String, dynamic>> getGroupSettings(String conversationId);
  Future<void> updateGroupSettings(String conversationId, Map<String, dynamic> settings);
  Future<void> transferOwnership(String conversationId, String newOwnerId);
  Future<void> updateGroupAdmins(String conversationId, List<String> adminIds);
  Future<void> dissolveConversation(String conversationId);
}
```

### KD-7：新增云端 API

| 接口 | 方法 | Body | 说明 |
|---|---|---|---|
| `GET /conversations/{id}/settings` | GET | — | 获取群设置 |
| `PATCH /conversations/{id}/settings` | PATCH | `{qrCodeJoinEnabled, ...}` | 更新群设置 |
| `PATCH /conversations/{id}/owner` | PATCH | `{newOwnerId}` | 转让群主 |
| `PUT /conversations/{id}/admins` | PUT | `{adminIds: [...]}` | 设置管理员 |
| `DELETE /conversations/{id}` | DELETE | — | 解散群聊 |

### KD-8：WebSocket 事件

| 事件 | 触发 | 说明 |
|---|---|---|
| `conv.settings.updated` | 设置变更 | 推送最新设置到所有成员 |
| `conv.owner.transferred` | 群主转让 | 推送新旧群主信息 |
| `conv.admins.updated` | 管理员变更 | 推送最新管理员列表 |
| `conv.dissolved` | 群被解散 | 通知所有成员 |

### KD-9：角色判断 Provider

```dart
final currentUserRoleProvider = FutureProvider.family<String, String>((ref, convId) async {
  final repo = ref.read(chatRepositoryProvider);
  final members = await repo.listMembers(conversationId: convId);
  final currentUserId = ref.read(currentUserIdProvider);
  final me = members.firstWhere((m) => m['userId'] == currentUserId, orElse: () => {});
  return me['role'] as String? ?? 'member';
});
```

## TDD / ATDD 策略

| Task | 验收项 | 测试层 | Red 先行 |
|---|---|---|---|
| T1: GroupSettings DTO | A2 | T1 | 序列化契约测试 |
| T2: GroupManagePage | A1~A2 | T2 | Widget test |
| T3: TransferOwnershipPage | A3 | T2/T3 | Widget test + 弹窗 |
| T4: GroupAdminsPage | A4 | T2 | Widget test 多选限制 |
| T5: 群名称权限拦截 | A5 | T2 | Widget test |
| T6: 隐私屏障权限 | A6 | T2/T4 | Widget test |
| T7: ChatRepository 扩展 | A8~A9 | T1/T3 | 契约测试 |
| T8: WS 事件 | A8/A11 | T2/T3 | 单元测试 |
| T9: 设置页头像 | A10 | T2 | Widget test |

## 未来演进

- 成员禁言（管理员专项能力）
- 群公告编辑权限
- 进群审批列表页面
