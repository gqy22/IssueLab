# GitHub App 快速配置清单

## ✅ 配置步骤

### 第一步：创建 GitHub App

- [ ] 访问 https://github.com/settings/apps/new
- [ ] 填写基本信息：
  - App name: `IssueLab Dispatcher`
  - Homepage URL: `https://github.com/gqy20/IssueLab`
- [ ] 配置权限：
  - [ ] Actions: **Read and write** ✅
  - [ ] Contents: **Read-only** ✅
  - [ ] Metadata: **Read-only** ✅（自动选中）
- [ ] 取消勾选 Webhook：`Active` ❌
- [ ] Where can install: 选择 **Any account**
- [ ] 点击 **Create GitHub App**

### 第二步：生成 Private Key

- [ ] 在 App 设置页面，找到 "Private keys" 部分
- [ ] 点击 **Generate a private key**
- [ ] 下载 `.pem` 文件并保存到安全位置
- [ ] 记录 **App ID**（在页面顶部）

### 第三步：安装 App 到主仓库

- [ ] 在 App 设置页面，点击 **Install App**
- [ ] 选择你的账户 `gqy20`
- [ ] 选择仓库：
  - [ ] `gqy20/IssueLab`
- [ ] 点击 **Install**

### 第四步：配置 Secrets

访问：https://github.com/gqy20/IssueLab/settings/secrets/actions

- [ ] 添加 **ISSUELAB_APP_ID**
  - Value: `你的 App ID`（数字）
- [ ] 添加 **ISSUELAB_APP_PRIVATE_KEY**
  - Value: 完整的 `.pem` 文件内容（包括 BEGIN 和 END 行）

### 第五步：通知 Fork 仓库主人

⚠️ **这是最关键的一步！**

发送以下消息给每个 fork 仓库的主人（如 gqy22）：

```markdown
Hi @gqy22,

为了让主仓库能够触发你的 fork 仓库的 agents，请安装以下 GitHub App：

**App 链接**：https://github.com/apps/YOUR_APP_NAME

**安装步骤**：
1. 点击上面的链接
2. 点击 "Install"
3. 选择 Only select repositories
4. 勾选 gqy22/IssueLab
5. 点击 Install

**权限说明**：
这个 App 只有以下权限：
- Actions: Read and write（触发你的 agent workflow）
- Contents: Read-only（读取配置文件）

安装后，当有人在主仓库 @gqy22 时，会自动触发你 fork 仓库的 agent。

配置文档：https://github.com/gqy20/IssueLab/blob/main/docs/GITHUB_APP_SETUP.md
```

### 第六步：Fork 仓库配置

每个 fork 仓库需要：

- [ ] 修改 `.github/workflows/user_agent.yml`
- [ ] 将触发器改为 `workflow_dispatch`
- [ ] 添加 `inputs` 定义（参考文档）

### 第七步：测试

- [ ] 在主仓库的任意 Issue 中评论：`@gqy22 测试`
- [ ] 检查主仓库 Actions：https://github.com/gqy20/IssueLab/actions
- [ ] 检查 fork 仓库 Actions：https://github.com/gqy22/IssueLab/actions
- [ ] 确认 workflow 被成功触发

---

## 🧪 验证命令

### 检查 App 是否安装

```bash
# 检查主仓库
gh api /repos/gqy20/IssueLab/installation

# 检查 fork 仓库（需要 App token）
gh api /repos/gqy22/IssueLab/installation
```

成功返回示例：
```json
{
  "id": 12345678,
  "account": {
    "login": "gqy20",
    "type": "User"
  },
  "app_id": 123456,
  "target_type": "User"
}
```

### 检查 Secrets 配置

```bash
# 列出所有 secrets（只显示名称，不显示值）
gh secret list -R gqy20/IssueLab
```

应该看到：
```
ISSUELAB_APP_ID              Updated 2024-01-01
ISSUELAB_APP_PRIVATE_KEY     Updated 2024-01-01
```

---

## 🐛 常见问题

### 问题：App 安装失败

**症状**：点击 Install 后返回错误

**解决**：
- 确保 App 配置中选择了 "Any account"
- 检查是否有足够的仓库权限

### 问题：Workflow 无法生成 token

**症状**：Workflow 失败，错误信息 "Could not create token"

**原因**：
1. Private key 格式不正确
2. App ID 不正确
3. App 未安装到仓库

**解决**：
- 重新复制 Private key，确保包含 BEGIN 和 END 行
- 检查 App ID 是否正确
- 确认 App 已安装到目标仓库

### 问题：Fork 仓库未被触发

**症状**：主仓库 dispatch 成功，但 fork 仓库没有运行

**原因**：
1. Fork 仓库未安装 App ← **最常见**
2. Fork 仓库的 workflow 未配置 workflow_dispatch
3. Workflow 文件名不匹配

**解决**：
- 确认 fork 仓库主人已安装 App
- 检查 fork 仓库的 workflow 配置
- 检查 registry 中的 `workflow_file` 配置

---

## 📋 配置对比

### GitHub App vs PAT

| 配置项 | GitHub App | PAT |
|--------|-----------|-----|
| 创建步骤 | 5 步 | 2 步 |
| 需要 fork 配合 | ✅ 需要安装 App | ✅ 需要提供 PAT |
| 安全性 | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| Token 管理 | 自动 | 手动 |
| 推荐程度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

---

## 📚 相关文档

- [完整配置指南](./GITHUB_APP_SETUP.md)
- [Dispatch 配置](./DISPATCH_SETUP.md)
- [Scripts README](../scripts/README.md)
