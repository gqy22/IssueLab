# GitHub App 配置指南

## 为什么使用 GitHub App？

相比 Personal Access Token (PAT)，GitHub App 具有以下优势：

| 特性 | PAT | GitHub App |
|------|-----|------------|
| **权限控制** | 全局权限 | 细粒度权限 |
| **作用范围** | 所有仓库 | 指定仓库 |
| **Token 过期** | 手动管理 | 自动刷新 |
| **审计日志** | 个人账户 | App 独立 |
| **跨仓库访问** | ✅ | ✅ |
| **Fork 仓库支持** | ⚠️ 受限 | ✅ 完整支持 |

## 🔧 配置步骤

### 步骤 1：创建 GitHub App

1. **访问创建页面**：
   - 个人账户：https://github.com/settings/apps/new
   - 组织账户：https://github.com/organizations/YOUR_ORG/settings/apps/new

2. **基本信息**：
   ```
   GitHub App name: IssueLab Dispatcher
   Homepage URL: https://github.com/gqy20/IssueLab
   Description: Cross-repository agent dispatcher for IssueLab
   ```

3. **权限配置**（Repository permissions）：
   ```
   ✅ Actions: Read and write
      - 必需：用于触发 workflow_dispatch

   ✅ Contents: Read-only
      - 必需：读取仓库内容

   ✅ Metadata: Read-only (自动选中)
      - 必需：基础元数据

   □ Issues: Read and write (可选)
      - 如果需要在 fork 仓库创建评论
   ```

4. **取消勾选 Webhook**：
   ```
   □ Active
      - 不需要 webhook，我们使用 Actions 触发
   ```

5. **Where can this GitHub App be installed?**
   ```
   ✅ Any account
      - 允许安装到 fork 仓库
   ```

6. **点击 "Create GitHub App"**

### 步骤 2：生成 Private Key

创建 App 后：

1. 进入 App 设置页面
2. 滚动到 "Private keys" 部分
3. 点击 **"Generate a private key"**
4. 下载 `.pem` 文件（例如：`issuelab-dispatcher.2024-01-01.private-key.pem`）

⚠️ **重要**：Private key 只能下载一次，请妥善保存！

### 步骤 3：获取 App ID

在 App 设置页面顶部找到：
```
App ID: 123456
```
记下这个数字。

### 步骤 4：安装 App 到仓库

#### 安装到主仓库 (gqy20/IssueLab)

1. 进入 App 设置页面
2. 点击左侧 **"Install App"** 标签
3. 找到你的账户，点击 **"Install"**
4. 选择仓库访问：
   ```
   ◉ Only select repositories
     ☑ gqy20/IssueLab
   ```
5. 点击 **"Install"**

#### 通知 Fork 仓库主人安装（关键！）

**这是最重要的一步！** Fork 仓库（如 gqy22/IssueLab）也必须安装这个 App。

发送以下信息给 fork 仓库主人（例如 gqy22）：

```markdown
## 请安装 IssueLab Dispatcher App

为了让主仓库能够触发你的 fork 仓库的 workflows，请安装以下 GitHub App：

**App 链接**：https://github.com/apps/issuelab-dispatcher

**安装步骤**：
1. 点击上面的链接
2. 点击 "Install"
3. 选择你的 fork 仓库：gqy22/IssueLab
4. 确认安装

**说明**：这个 App 只有以下权限：
- Actions: Read and write（用于触发你的 agent workflow）
- Contents: Read-only（读取配置文件）

安装后，当有人在主仓库 @gqy22 时，会自动触发你 fork 仓库的 agent。
```

### 步骤 5：配置 Secrets

将 App 信息添加到主仓库的 secrets：

1. **访问 Secrets 页面**：
   https://github.com/gqy20/IssueLab/settings/secrets/actions

2. **添加 App ID**：
   - 点击 "New repository secret"
   - Name: `ISSUELAB_APP_ID`
   - Secret: `123456`（你的 App ID）

3. **添加 Private Key**：
   - 点击 "New repository secret"
   - Name: `ISSUELAB_APP_PRIVATE_KEY`
   - Secret: 打开 `.pem` 文件，复制完整内容（包括 BEGIN 和 END）：
     ```
     -----BEGIN RSA PRIVATE KEY-----
     MIIEpAIBAAKCAQEA...
     ...（完整的 key 内容）...
     -----END RSA PRIVATE KEY-----
     ```

### 步骤 6：更新 Workflow 文件（已完成）

主仓库的 workflow 已配置为使用 GitHub App token：

```yaml
- name: Generate GitHub App Token
  id: app-token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.ISSUELAB_APP_ID }}
    private-key: ${{ secrets.ISSUELAB_APP_PRIVATE_KEY }}

- name: Dispatch to user repositories
  env:
    GITHUB_TOKEN: ${{ steps.app-token.outputs.token }}
  run: |
    python scripts/dispatch_to_users.py ...
```

### 步骤 7：Fork 仓库配置 workflow_dispatch

Fork 仓库需要更新 workflow 以支持 `workflow_dispatch`。

**gqy22 需要在他的仓库修改：**

```yaml
# gqy22/IssueLab/.github/workflows/user_agent.yml
name: Run Agent on Repository Dispatch

on:
  workflow_dispatch:  # 改为 workflow_dispatch
    inputs:
      source_repo:
        description: 'Source repository'
        required: true
        type: string
      issue_number:
        description: 'Issue number'
        required: true
        type: string
      issue_title:
        required: false
        type: string
      issue_body:
        required: false
        type: string
      comment_id:
        required: false
        type: string
      comment_body:
        required: false
        type: string
      labels:
        required: false
        type: string
      target_username:
        required: false
        type: string

jobs:
  run-agent:
    runs-on: ubuntu-latest
    steps:
      - name: Display trigger info
        run: |
          echo "Triggered from: ${{ inputs.source_repo }}"
          echo "Issue #${{ inputs.issue_number }}"
          echo "Agent: ${{ inputs.target_username }}"

      # ... 其他步骤
```

---

## 🧪 测试配置

### 1. 验证 App 安装

```bash
# 检查主仓库的安装
gh api /repos/gqy20/IssueLab/installation

# 检查 fork 仓库的安装（如果有权限）
gh api /repos/gqy22/IssueLab/installation
```

如果返回 `404`，说明 App 未安装到该仓库。

### 2. 测试 Token 生成

在本地测试生成 installation token：

```bash
# 需要安装 jwt-cli
# npm install -g jwt-cli

# 生成 JWT
APP_ID="123456"
PRIVATE_KEY_PATH="path/to/your-app.private-key.pem"

# 创建 JWT（有效期 10 分钟）
JWT=$(jwt encode \
  --iss "$APP_ID" \
  --exp "+10 minutes" \
  --alg RS256 \
  --secret "@$PRIVATE_KEY_PATH")

# 获取 installation ID
INSTALLATION_ID=$(curl -s \
  -H "Authorization: Bearer $JWT" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/gqy22/IssueLab/installation \
  | jq -r .id)

# 生成 installation token
INSTALLATION_TOKEN=$(curl -s -X POST \
  -H "Authorization: Bearer $JWT" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/app/installations/$INSTALLATION_ID/access_tokens \
  | jq -r .token)

echo "Installation Token: $INSTALLATION_TOKEN"
```

### 3. 测试 Workflow Dispatch

在 Issue 中评论：
```markdown
@gqy22 测试 GitHub App dispatch
```

查看 Actions 运行：
- 主仓库：https://github.com/gqy20/IssueLab/actions
- Fork 仓库：https://github.com/gqy22/IssueLab/actions

---

## 🐛 故障排查

### 问题 1：401 Unauthorized

**错误信息**：
```
Error: HTTP 401: Bad credentials
```

**原因**：
- Private key 不正确
- App ID 不正确
- Secrets 配置错误

**解决方案**：
1. 检查 `ISSUELAB_APP_ID` 是否正确
2. 重新复制 Private key，确保包含 BEGIN 和 END 行
3. 确保 Private key 没有额外的空格或换行

### 问题 2：404 Not Found (Installation)

**错误信息**：
```
Error: HTTP 404: Not Found
Could not retrieve installation for repository
```

**原因**：App 未安装到目标仓库

**解决方案**：
1. 确认 App 已安装到主仓库（gqy20/IssueLab）
2. **确认 App 已安装到 fork 仓库**（gqy22/IssueLab）← 最常见的问题！
3. 检查 App 的仓库访问权限

### 问题 3：403 Forbidden (Workflow Dispatch)

**错误信息**：
```
Error: HTTP 403: Resource not accessible
```

**原因**：
- Fork 仓库未安装 App
- App 权限不足（缺少 Actions: write）
- Workflow 未配置 workflow_dispatch

**解决方案**：
1. 确保 fork 仓库主人已安装 App
2. 检查 App 权限配置
3. 确认 fork 仓库的 workflow 使用 `workflow_dispatch` 触发

### 问题 4：Token 过期

**说明**：GitHub App token 默认有效期 1 小时，但会自动刷新。

如果在 workflow 中遇到过期问题：
- `actions/create-github-app-token` 会自动处理刷新
- 无需手动操作

---

## 📊 权限对比

### GitHub App vs PAT

| 场景 | PAT | GitHub App |
|------|-----|------------|
| 触发主仓库 workflow | ✅ | ✅ |
| 触发 fork 仓库 workflow | ❌ 需要 fork 主人的 PAT | ✅ Fork 主人安装 App 即可 |
| 权限范围 | 所有仓库或部分仓库 | 精确到单个仓库 |
| Token 管理 | 手动更新 | 自动刷新 |
| 安全性 | ⭐⭐ | ⭐⭐⭐⭐ |
| 配置复杂度 | ⭐ 简单 | ⭐⭐⭐ 中等 |

---

## 🔒 安全最佳实践

### 1. 最小权限原则

只授予必要的权限：
```
✅ Actions: Read and write
✅ Contents: Read-only
✅ Metadata: Read-only
❌ 不要授予不必要的权限
```

### 2. 定期轮换 Private Key

建议每 6-12 个月轮换一次：
1. 在 App 设置中生成新的 Private Key
2. 更新 `ISSUELAB_APP_PRIVATE_KEY` secret
3. 删除旧的 Private Key

### 3. 限制 App 安装范围

```
◉ Only select repositories
  ☑ gqy20/IssueLab
  （只安装到需要的仓库）
```

### 4. 监控 App 活动

定期检查 App 的活动日志：
- 访问：https://github.com/settings/apps/YOUR_APP/advanced
- 查看 "Recent Deliveries"（如果启用了 webhook）

---

## 📚 相关资源

- [GitHub Apps 文档](https://docs.github.com/en/apps)
- [actions/create-github-app-token](https://github.com/actions/create-github-app-token)
- [Authenticating with GitHub Apps](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app)
- [GitHub App 权限](https://docs.github.com/en/rest/overview/permissions-required-for-github-apps)

---

## 🎯 快速检查清单

在测试前，确保完成以下步骤：

- [ ] 创建 GitHub App
- [ ] 生成并保存 Private Key (.pem 文件)
- [ ] 记录 App ID
- [ ] 安装 App 到主仓库（gqy20/IssueLab）
- [ ] **通知并确保 fork 仓库主人安装了 App**
- [ ] 添加 `ISSUELAB_APP_ID` secret
- [ ] 添加 `ISSUELAB_APP_PRIVATE_KEY` secret
- [ ] 更新主仓库 workflow（已完成）
- [ ] Fork 仓库更新为 workflow_dispatch 触发
- [ ] 在 Issue 中测试 @mention

---

**最关键的一点**：Fork 仓库（gqy22/IssueLab）必须安装这个 GitHub App！否则主仓库无法触发 fork 仓库的 workflow。
