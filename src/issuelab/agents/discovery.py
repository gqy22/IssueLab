"""Agent 发现和管理

动态发现并管理系统中的所有 Agent 配置。
"""

import re
from pathlib import Path

# 提示词目录
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"
AGENTS_DIR = Path(__file__).parent.parent.parent.parent / "agents"


def parse_agent_metadata(content: str) -> dict | None:
    """从 prompt 文件中解析 YAML 元数据

    格式：
    ---
    agent: moderator
    description: 分诊与控场代理
    trigger_conditions:
      - 新论文 Issue
      - 需要分配评审流程
    ---
    """
    # 匹配 YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return None

    yaml_str = match.group(1)
    metadata = {}
    current_list_key = None
    current_list = []

    # 解析 YAML
    for line in yaml_str.split("\n"):
        line = line.rstrip()

        # 检测列表项
        if line.strip().startswith("- "):
            item = line.strip()[2:].strip()
            current_list.append(item)
            # 找到最后一个列表键
            for key in ["trigger_conditions"]:
                if key in metadata:
                    current_list_key = key
            continue

        # 检测普通键值对
        if ":" in line and not line.strip().startswith("-"):
            # 先保存之前的列表
            if current_list and current_list_key:
                metadata[current_list_key] = current_list
                current_list = []
                current_list_key = None

            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if value:
                metadata[key] = value
            else:
                metadata[key] = None

    # 保存最后的列表
    if current_list and current_list_key:
        metadata[current_list_key] = current_list

    return metadata if metadata else None


def discover_agents() -> dict:
    """动态发现所有可用的 Agent

    通过读取 prompts 文件夹下的 .md 文件，解析 YAML 元数据

    Returns:
        {
            "agent_name": {
                "description": "Agent 描述",
                "prompt": "完整 prompt 内容",
                "trigger_conditions": ["触发条件1", "触发条件2"],
            }
        }
    """
    agents = {}

    if not PROMPTS_DIR.exists():
        return agents

    # 扫描 prompts 目录下的 .md 文件
    for prompt_file in PROMPTS_DIR.glob("*.md"):
        content = prompt_file.read_text()
        metadata = parse_agent_metadata(content)

        if metadata and "agent" in metadata:
            agent_name = metadata["agent"]
            # 移除 frontmatter，获取纯 prompt 内容
            clean_content = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()

            agents[agent_name] = {
                "description": metadata.get("description", ""),
                "prompt": clean_content,
                "trigger_conditions": metadata.get("trigger_conditions", []),
            }

    # 扫描 agents 目录下的用户自定义 agent
    if AGENTS_DIR.exists():
        import yaml

        for agent_dir in AGENTS_DIR.iterdir():
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue

            agent_file = agent_dir / "agent.yml"
            prompt_file = agent_dir / "prompt.md"

            if not agent_file.exists() or not prompt_file.exists():
                continue

            # 使用目录名作为 agent_id
            agent_name = agent_dir.name

            # 从 agent.yml 读取配置
            with open(agent_file, encoding="utf-8") as f:
                agent_config = yaml.safe_load(f)

            # 读取 prompt 内容（移除可能的 frontmatter）
            prompt_content = prompt_file.read_text()
            # 移除 frontmatter（兼容旧格式）
            prompt_content = re.sub(r"^---\n.*?\n---\n", "", prompt_content, flags=re.DOTALL).strip()

            agents[agent_name] = {
                "description": agent_config.get("description", ""),
                "prompt": prompt_content,
                "trigger_conditions": agent_config.get("triggers", []),
            }

    return agents


def get_agent_matrix_markdown() -> str:
    """生成 Agent 矩阵的 Markdown 表格（用于 Observer Prompt）"""
    agents = discover_agents()

    lines = [
        "| Agent | 描述 | 何时触发 |",
        "|-------|------|---------|",
    ]

    for name, config in agents.items():
        if name == "observer":
            continue  # Observer 不需要被自己触发
        trigger_conditions = config.get("trigger_conditions", [])
        trigger = ", ".join(trigger_conditions) if trigger_conditions else "自动判断"
        desc = config.get("description", "")
        lines.append(f"| **{name}** | {desc} | {trigger} |")

    return "\n".join(lines)


def load_prompt(agent_name: str) -> str:
    """加载代理提示词（从动态发现的 agents 中）"""
    agents = discover_agents()
    if agent_name in agents:
        return agents[agent_name]["prompt"]
    return ""
