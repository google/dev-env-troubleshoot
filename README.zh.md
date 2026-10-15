# gcheck CLI

[English](README.md) | **中文** | [Español](README.es.md) | [日本語](README.ja.md)

gcheck 是一款专为开发者打造的轻量级 CLI 诊断工具，旨在简化 Google AI 的集成流程。无需再手写临时脚本测试 API —— 它能在几秒内自动扫描你的本地配置，助你尽早发现配置问题，让第一个 "Hello Gemini" 顺利跑通。

---

## ✨ 核心特性

- 🚀 **自动化 Gemini API 诊断**：快速排查 Google Gemini API 调用问题。自动校验网络连通性、Google Cloud Platform (GCP) 项目权限、API 密钥与模型参数配置，助你更快接入 Gemini。
- 📁 **智能项目目录扫描**：直接在你的工作区内无缝检测项目配置。深度分析本地环境配置文件、依赖项与相关设置，精准定位潜在的集成瓶颈。
- 🛠️ **告别晦涩报错，直接给出修复方案**：不仅能定位问题，更助你快速修复。将令人费解的报错信息转化为清晰易懂的说明，并提供可执行的分步排障指引，彻底告别盲目试错。

---

## 📋 前置要求

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/installation/)（推荐的安装方式；若直接使用 `pip` 则无需安装）
- `GEMINI_API_KEY`（可选 —— 仅在需要验证 Gemini API 连通性时才需提供）

---

## 🚀 安装指南

### 快速安装（推荐）

克隆仓库后，运行对应操作系统的安装脚本。该脚本会自动检测 Python 3.10+ 与 `pipx`（若缺失会自动安装），并将 `gcheck` 安装为全局、可编辑的命令行工具 —— 后续修改代码无需重新安装，立即生效：

```sh
# macOS / Linux
./install.sh
```

```powershell
# Windows (PowerShell)
.\install.ps1
```

如果 macOS/Linux 提示 `permission denied`（权限不足），请先添加执行权限，然后重新运行：

```sh
chmod +x install.sh
./install.sh
```

如果 Windows 提示执行策略错误（execution-policy error），请执行：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

如果安装完成后提示找不到 `gcheck` 命令，请打开一个新的终端窗口 —— 安装脚本可能刚刚更新了你的 `PATH` 环境变量。

### 手动安装

| 命令 | 独立虚拟环境 | 全局 `gcheck` 命令 | 可编辑模式（代码修改立即生效） |
|---|---|---|---|
| `pipx install --editable .`（推荐） | 是 | 是 | 是 |
| `pipx install .` | 是 | 是 | 否 —— 修改后需加 `--force` 重新安装 |
| `pip install -e .` | 否，安装至当前激活环境 | 是，仅限该环境内生效 | 是 |
| `pip install --require-hashes -r requirements.txt` | 否，安装至当前激活环境 | 否 —— 无入口命令，需通过 `python -m gcheck` 运行 | 不适用 |

```sh
# 日常开发调试推荐使用
pipx install --editable .
```

`pip install --require-hashes -r requirements.txt` 会从锁定文件中安装经过哈希校验的精确版本依赖，但不会安装 `gcheck` 本身 —— 可用于复现已知可用的依赖集合，随后仍需运行 `pip install -e . --no-deps` 来获得 `gcheck` 命令。

---

## ⚙️ 配置说明

可选 —— 仅在进行 API 密钥连通性检查时需要。将工作目录下的 `.env.example` 复制为 `.env`，并填入你的 API 密钥：

```
GEMINI_API_KEY=your_api_key_here
```

---

## 💻 使用方法

```sh
gcheck              # 在终端交互界面 (TUI) 中选择语言
gcheck --lang en    # 英文 (English)
gcheck --lang zh    # 中文
gcheck --lang es    # 西班牙语 (Español)
gcheck --lang ja    # 日语 (日本語)
```

---

## 🗑️ 卸载指南

```sh
pipx uninstall gcheck
```

如果提示 `pipx: command not found` —— `install.sh` 可能是通过 `pip install --user`（而非 Homebrew）安装的 `pipx`，这种方式仅在*新打开的*终端窗口中才会将其加入 `PATH`。你可以打开一个新终端重试，或者直接通过 Python 运行卸载：

```sh
python3 -m pipx uninstall gcheck
```

如果你是通过 `pip install -e .` 而非 `pipx` 安装的，请在当时安装的同一 Python 环境中执行 `pip uninstall gcheck`。

若需一并移除 `pipx` 本身：先执行 `pipx uninstall-all`（移除所有由 pipx 管理的应用），然后根据最初安装 `pipx` 的方式，执行 `pip uninstall pipx` 或 `brew uninstall pipx`。

---

## 🧪 测试

测试套件基于本地检出的代码运行：

```sh
pip install -e ".[test]"
pytest unit_test
```

每次 push 和 pull request 时，CI 都会在 Ubuntu、macOS 和 Windows 系统上的 Python 3.10 与 3.13 环境中运行相同的测试套件 —— 详见 [.github/workflows/unit-tests.yml](.github/workflows/unit-tests.yml)。关于已覆盖及刻意未覆盖的测试内容，请参阅 [unit_test/README.md](unit_test/README.md)。

---

## 📄 开源协议

本项目采用 Apache License 2.0 协议开源。完整协议内容请参阅 [LICENSE](LICENSE) 文件。
