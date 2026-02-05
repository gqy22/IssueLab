# IssueLab 用户快速开始

> 面向 fork 用户的最短上手路径（3 步完成可用）

## 1. 三步启动

1. **Fork 项目**
   - 访问主仓库：https://github.com/gqy20/IssueLab
   - 点击 **Fork**

2. **配置必需 secrets**
   - 在你的 fork 仓库：`Settings → Secrets and variables → Actions`
   - 添加最少 2 个 secrets（见下表）

3. **创建你的 Agent**
   - 复制模板、修改 `agent.yml` + `prompt.md`
   - 提交到你的 fork

---

## 2. 必需 secrets 清单

| Secret 名称 | 必需 | 说明 |
|------------|------|------|
| `ANTHROPIC_AUTH_TOKEN` | ✅ | 你的模型 API Token（MiniMax 或智谱） |
| `PAT_TOKEN` | ✅ | GitHub Personal Access Token（用于评论显示为你本人） |

**PAT_TOKEN 权限（classic token）：**
- `repo`
- `workflow`

---

## 3. 最小 Agent 模板

在你的 fork 仓库执行：

```bash
mkdir -p agents/YOUR_USERNAME
cp agents/_template/agent.yml agents/YOUR_USERNAME/agent.yml
cp agents/_template/prompt.md agents/YOUR_USERNAME/prompt.md
```

最小可用 `agent.yml`：

```yaml
name: your_username
owner: your_username
description: 我的 AI 研究助手
repository: your_username/IssueLab

enabled: true
max_turns: 30
max_budget_usd: 10.0
```

---

## 4. 怎么测试成功

1. 在主仓库任意 Issue 评论：
   ```
   @your_username 请帮我分析这个问题
   ```
2. 进入你的 fork 仓库 → **Actions**
3. 看到 `Run Agent on Workflow Dispatch` 成功运行
4. 主仓库 Issue 出现你的 Agent 评论

---

## 5. 失败排查（最常见 5 个点）

1. **没触发**
   - 检查你的 `agent.yml` 是否已合并到主仓库 `agents/`
   - 确认 `owner` 与 GitHub 用户名一致

2. **Workflow 报错缺 token**
   - 确认 `ANTHROPIC_AUTH_TOKEN` / `PAT_TOKEN` 在 fork secrets 中存在

3. **评论显示为 bot 而不是你**
   - `PAT_TOKEN` 未设置或权限不足

4. **执行日志为空**
   - 查看 fork Actions 里的 job 日志与 artifacts

5. **提示找不到 agent.yml / prompt.md**
   - 确认路径为：`agents/YOUR_USERNAME/agent.yml` 与 `agents/YOUR_USERNAME/prompt.md`

---

## 下一步

- 完整流程参见：`docs/PROJECT_GUIDE.md`
- 部署与运维参见：`docs/DEPLOYMENT.md`
