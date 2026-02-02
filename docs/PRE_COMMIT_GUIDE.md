# Pre-commit Hooks 使用指南

本项目使用 [pre-commit](https://pre-commit.com/) 来确保代码质量和一致性。

## 🚀 快速开始

### 1. 安装 pre-commit

```bash
# 使用 uv 安装（推荐）
uv pip install pre-commit

# 或者安装开发依赖
uv sync --group dev
```

### 2. 安装 git hooks

```bash
uv run pre-commit install
```

安装完成后，每次 `git commit` 时会自动运行检查。

### 3. 手动运行检查

```bash
# 检查所有文件
uv run pre-commit run --all-files

# 仅检查暂存的文件
uv run pre-commit run
```

## 🔧 配置的检查项

### Ruff - Python 代码检查和格式化
- **Linting**: 检查代码风格、潜在错误、复杂度等
- **Formatting**: 自动格式化代码（双引号、缩进等）
- **Auto-fix**: 自动修复可修复的问题

### 基础文件检查
- ✅ 移除行尾空白
- ✅ 确保文件以换行符结尾
- ✅ 检查 YAML 语法
- ✅ 检查 TOML 语法
- ✅ 检查大文件（>1MB）
- ✅ 检查合并冲突标记
- ✅ 检查 debug 语句（如 `breakpoint()`）

## 📋 启用的 Ruff 规则

配置在 `pyproject.toml` 中：

| 规则集 | 说明 |
|-------|------|
| `E`   | pycodestyle errors |
| `W`   | pycodestyle warnings |
| `F`   | pyflakes（未使用导入等） |
| `I`   | isort（导入排序） |
| `N`   | pep8-naming（命名规范） |
| `UP`  | pyupgrade（现代 Python 语法） |
| `B`   | flake8-bugbear（常见错误模式） |
| `C4`  | flake8-comprehensions（推导式优化） |
| `SIM` | flake8-simplify（代码简化） |

## 🎯 与 CI 保持一致

pre-commit 配置与 CI 管道完全一致：

```
本地 pre-commit → GitHub Actions CI
     ↓                    ↓
   ruff check         ruff check
   ruff format        ruff format
```

这确保了：
- ✅ 本地提交前发现问题
- ✅ CI 不会因格式问题失败
- ✅ 代码风格保持一致

## 💡 常见使用场景

### 跳过 hooks（不推荐）
```bash
git commit --no-verify -m "message"
```

### 更新 pre-commit hooks
```bash
uv run pre-commit autoupdate
```

### 卸载 hooks
```bash
uv run pre-commit uninstall
```

## 🔍 故障排除

### 问题：pre-commit 运行很慢
**解决**：首次运行需要安装环境，之后会缓存并快速运行。

### 问题：某些文件被修改但 hook 失败
**解决**：这是正常的，pre-commit 自动修复了文件。重新 `git add` 并提交：
```bash
git add .
git commit -m "message"
```

### 问题：想要手动格式化单个文件
**解决**：直接使用 ruff：
```bash
# 检查
uv run ruff check src/issuelab/file.py

# 格式化
uv run ruff format src/issuelab/file.py
```

## 📚 相关资源

- [pre-commit 官方文档](https://pre-commit.com/)
- [Ruff 文档](https://docs.astral.sh/ruff/)
- [项目 CI 配置](.github/workflows/ci.yml)
