# Agent Dispatch 配置指南

## 📋 概述

IssueLab 支持两种 Dispatch 模式，用于触发 fork 仓库中的 agent workflows：

1. **repository_dispatch** - 适用于主仓库或非 fork 仓库
2. **workflow_dispatch** - 适用于 fork 仓库（推荐）

## 🔑 认证方式选择

### 方式 1：GitHub App（推荐 ⭐⭐⭐⭐⭐）

**优势：**
- ✅ 更安全的细粒度权限
- ✅ Token 自动刷新，无需手动管理
- ✅ 支持跨账户（fork 仓库）访问
- ✅ 独立审计日志
- ✅ 无需共享个人 PAT

**配置指南：** 📖 [GitHub App 完整配置](./GITHUB_APP_SETUP.md)

**快速步骤：**
1. 创建 GitHub App
2. 生成 Private Key
3. 安装到主仓库和 fork 仓库
4. 配置 secrets：`ISSUELAB_APP_ID` 和 `ISSUELAB_APP_PRIVATE_KEY`

### 方式 2：Personal Access Token (PAT)

**适用场景：**
- 快速测试
- 简单的个人项目
- 不想创建 GitHub App

**限制：**
- ⚠️ 需要定期手动更新（过期时间）
- ⚠️ 权限范围较大
- ⚠️ 依赖个人账户

---

## 🔧 方式 2：配置 PAT Token

### 1. 配置 PAT Token

在主仓库（gqy20/IssueLab）中配置 Personal Access Token：

1. 创建 PAT：https://github.com/settings/tokens/new
   - Token name: `IssueLab Workflow Dispatcher`
   - Expiration: 90 days 或更长
   - 权限：
     - ✅ `repo` (Full control of private repositories)
     - ✅ `workflow` (Update GitHub Action workflows)

2. 添加到仓库 secrets：
   - 访问：https://github.com/gqy20/IssueLab/settings/secrets/actions/new
   - Name: `PAT_TOKEN`（如使用 PAT）或已配置 GitHub App
   - Secret: 粘贴步骤 1 的 token

⚠️ **如果已配置 GitHub App**，可以跳过此步骤，workflow 会自动使用 App token。

### 2. 验证 Token 权限

运行以下命令验证 token 配置：

```bash
# 设置环境变量
export PAT_TOKEN="ghp_your_token_here"

# 检查权限
curl -H "Authorization: Bearer $PAT_TOKEN" \
     -I https://api.github.com/rate_limit | grep x-oauth-scopes

# 应该看到：x-oauth-scopes: repo, workflow
```

---

## 🔧 配置 Agent Registry

### 方案 A：使用 workflow_dispatch（推荐用于 fork 仓库）

编辑 `agents/_registry/{username}.yml`：

```yaml
username: gqy22
display_name: "gqy22"
repository: gqy22/IssueLab
branch: main

# 关键配置：使用 workflow_dispatch 模式
dispatch_mode: workflow_dispatch
workflow_file: user_agent.yml

triggers:
  - "@gqy22"

enabled: true
type: reviewer
```

**Fork 仓库需要配合修改：**

在 fork 仓库（gqy22/IssueLab）中修改 `.github/workflows/user_agent.yml`：

```yaml
name: Run Agent on Repository Dispatch

on:
  workflow_dispatch:  # 改为 workflow_dispatch
    inputs:
      source_repo:
        description: 'Source repository (owner/repo)'
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
        description: 'Labels (JSON array)'
        required: false
        type: string
      target_username:
        required: false
        type: string

jobs:
  run-agent:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Display inputs
        run: |
          echo "Source: ${{ inputs.source_repo }}"
          echo "Issue: ${{ inputs.issue_number }}"
          echo "Agent: ${{ inputs.target_username }}"

      # ... 其他步骤，使用 inputs.xxx 而非 github.event.client_payload.xxx
```

### 方案 B：使用 repository_dispatch（默认，用于主仓库）

```yaml
username: gqy20
display_name: "IssueLab 官方"
repository: gqy20/IssueLab
branch: main

# 使用默认模式（可省略）
dispatch_mode: repository_dispatch

triggers:
  - "@gqy20"

enabled: true
type: moderator
```

---

## 🧪 测试 Dispatch 配置

### 方法 1：Dry-run 模式

在本地测试配置是否正确：

```bash
cd /workspaces/IssueLab

# 设置环境变量
export GITHUB_TOKEN="$PAT_TOKEN"

# Dry-run 测试（不实际发送）
python scripts/dispatch_to_users.py \
  --mentions "gqy22" \
  --registry-dir agents/_registry \
  --source-repo "gqy20/IssueLab" \
  --issue-number 1 \
  --issue-title "Test dispatch" \
  --dry-run
```

预期输出：
```
Found mentions: gqy22
Loaded 2 registered agents
Matched 1 agents
[DRY RUN] Would dispatch to gqy22/IssueLab
  Mode: workflow_dispatch
  Branch: main
  Workflow file: user_agent.yml
  Payload keys: source_repo, issue_number, issue_title, target_username, target_branch

============================================================
✅ Successfully dispatched to 1/1 agents
============================================================
```

### 方法 2：实际触发测试

在 Issue 中发送测试评论：

```markdown
@gqy22 请测试 dispatch 配置
```

查看 Actions 运行结果：
- 主仓库：https://github.com/gqy20/IssueLab/actions/workflows/dispatch_agents.yml
- Fork 仓库：https://github.com/gqy22/IssueLab/actions/workflows/user_agent.yml

---

## 🐛 故障排查

### 问题 1：403 Forbidden (repository_dispatch)

**错误信息：**
```
✗ 403 Forbidden: Cannot dispatch to gqy22/IssueLab
  💡 Suggestion: This may be a fork repository.
     Ask gqy22 to configure workflow_dispatch mode.
```

**原因：** GitHub 不允许跨用户的 `repository_dispatch` 触发 fork 仓库。

**解决方案：**
1. 修改 registry 配置为 `dispatch_mode: workflow_dispatch`
2. 通知 fork 仓库主人修改 workflow 使用 `workflow_dispatch` 触发

### 问题 2：404 Not Found (workflow_dispatch)

**错误信息：**
```
✗ 404 Not Found: gqy22/IssueLab/actions/workflows/user_agent.yml
  Workflow file may not exist or workflow_dispatch not configured
```

**原因：**
- Workflow 文件不存在
- Workflow 未配置 `workflow_dispatch` 触发器
- 文件名不匹配

**解决方案：**
1. 确认 workflow 文件存在：`gh api /repos/gqy22/IssueLab/actions/workflows`
2. 检查 registry 中的 `workflow_file` 配置是否正确
3. 确保 workflow 包含 `on: workflow_dispatch:` 配置

### 问题 3：PAT Token 权限不足

**错误信息：**
```
✗ 403 Forbidden: Cannot trigger workflow in gqy22/IssueLab
  Token may lack 'workflow' permission
```

**解决方案：**
1. 重新创建 PAT，确保勾选 `workflow` 权限
2. 更新仓库 secret `PAT_TOKEN`
3. 重新运行 workflow

### 问题 4：超时或网络错误

**错误信息：**
```
⚠️ Attempt 1/3 failed: HTTPSConnectionPool(...): Read timed out
   Retrying in 2.0s...
```

**说明：** 系统会自动重试 3 次，通常会成功。如果持续失败，检查网络连接。

---

## 📊 对比两种模式

| 特性 | repository_dispatch | workflow_dispatch |
|------|---------------------|-------------------|
| 支持 fork 仓库 | ❌ 不支持 | ✅ 支持 |
| 配置复杂度 | ⭐ 简单 | ⭐⭐ 中等 |
| 安全性 | ⭐⭐ 较低 | ⭐⭐⭐ 较高 |
| GitHub 推荐 | ❌ | ✅ |
| 需要 fork 修改 | ❌ | ✅ |

---

## 🎯 推荐配置流程

### 对于新用户（fork 仓库）：

1. **在主仓库注册**
   - 创建 `agents/_registry/{username}.yml`
   - 设置 `dispatch_mode: workflow_dispatch`

2. **修改自己的 fork**
   - 更新 `.github/workflows/user_agent.yml`
   - 改用 `workflow_dispatch` 触发

3. **测试**
   - 在主仓库 Issue 中 @mention 自己
   - 检查 Actions 是否被触发

### 对于主仓库管理员：

1. **配置 PAT_TOKEN**（一次性）
2. **审核新用户的 PR**（registry 文件）
3. **提醒用户修改 fork 仓库配置**

---

## 📚 相关文件

- **Dispatch 实现**: [src/issuelab/cli/dispatch.py](../src/issuelab/cli/dispatch.py)
- **Workflow 配置**: [.github/workflows/dispatch_agents.yml](../.github/workflows/dispatch_agents.yml)
- **Registry 模板**: [agents/_template/agent.yml](../agents/_template/agent.yml)
- **Scripts README**: [scripts/README.md](../scripts/README.md)

---

## 💡 最佳实践

1. **优先使用 workflow_dispatch**：更安全，更符合 GitHub 的设计理念
2. **设置合理的 rate_limit**：避免滥用 API
3. **启用 dry-run 测试**：先验证配置再实际运行
4. **定期更新 PAT**：设置 90 天过期，到期前更新
5. **监控失败率**：如果某个 agent 持续失败，检查配置

---

## 🔗 相关链接

- [GitHub API: Repository Dispatch](https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event)
- [GitHub API: Workflow Dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
