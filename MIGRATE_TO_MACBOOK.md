# 迁移 `GenericAgent_dev` 到本地 MacBook（Apple Silicon）

这份说明针对当前仓库的实际状态：

- 代码主线在 Git 仓库中维护
- 当前目录是一个 Git worktree，`.git` 不是目录，不能直接原样复制到 Mac 后继续正常使用 Git
- `mykey.py` 和 `compare_lab` 历史 runs 属于本地研究状态，需要单独迁移
- 目标机器是 **Apple Silicon macOS**

## 推荐迁移方式

迁移分两层：

1. **Git 层**
   - 先在 Linux 上把当前 `dev` worktree 的源码整理成正式提交
   - 合并到 `main`
   - push 到 `origin`
   - 然后在 Mac 上重新 `git clone`

2. **本地研究状态层**
   - 额外把本地配置和实验产物打包：
     - `GenericAgent/mykey.py`
     - `GenericAgent_LDY/mykey.py`
     - `compare_lab/runs/`
     - `compare_lab/web/runs/`
   - Mac 上 clone 完仓库后，再把这些内容解包进去

这样得到的结果是：

- Git 历史完整
- 当前源码状态完整
- 本地研究资产也完整
- 不会把 Linux worktree 的 `.git` 绝对路径带坏到 Mac

## Linux 源端步骤

### 1. 确认源码已经进入 Git

当前仓库根目录是 worktree：

```bash
cat .git
```

你会看到类似：

```text
gitdir: /fudan_university_cfs/yj/GenericAgent/.git/worktrees/GenericAgent_dev
```

所以必须先把当前代码提交到 Git，而不是直接拷贝整个目录给 Mac。

### 2. 打包本地研究状态

在仓库根目录执行：

```bash
bash scripts/export_mac_research_bundle.sh
```

默认会生成：

```text
dist/GenericAgent_dev_mac_local_state_<timestamp>.tar.gz
```

里面包含：

- `GenericAgent/mykey.py`（如果存在）
- `GenericAgent_LDY/mykey.py`（如果存在）
- `compare_lab/runs/`
- `compare_lab/web/runs/`

不包含：

- `temp/`
- `__pycache__/`
- `.venv/`
- Git 元数据

### 3. 把 bundle 传到 Mac

推荐用 `scp` 或 `rsync`：

```bash
scp dist/GenericAgent_dev_mac_local_state_*.tar.gz <mac_user>@<mac_host>:~/Downloads/
```

或：

```bash
rsync -avz --progress dist/GenericAgent_dev_mac_local_state_*.tar.gz <mac_user>@<mac_host>:~/Downloads/
```

## Mac 目标端步骤

### 1. 安装基础工具

```bash
xcode-select --install
```

如果没有 Homebrew：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

然后安装：

```bash
brew install git python@3.12 rsync
brew install --cask google-chrome
```

### 2. 重新 clone 仓库

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/YJGoodbye2024/GenericAgent.git GenericAgent_dev
cd GenericAgent_dev
git checkout main
```

不要把 Linux 上的 `.git` 文件直接复制到 Mac。

### 3. 建立 Python 环境

```bash
cd ~/Projects/GenericAgent_dev
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install requests beautifulsoup4 bottle simple-websocket-server streamlit pywebview
```

这一步只装基础依赖。其余依赖仍然可以让 Agent 自己按任务逐步安装。

### 4. 解包本地研究状态

假设 bundle 在 `~/Downloads/`：

```bash
cd ~/Projects/GenericAgent_dev
tar -xzf ~/Downloads/GenericAgent_dev_mac_local_state_*.tar.gz
```

这个 bundle 里的相对路径会直接覆盖到当前仓库目录中。

### 5. 先验证 CLI，再验证 GUI

#### GenericAgent

```bash
cd ~/Projects/GenericAgent_dev/GenericAgent
source ../.venv/bin/activate
python3 agentmain.py
```

#### GenericAgent_LDY

```bash
cd ~/Projects/GenericAgent_dev/GenericAgent_LDY
source ../.venv/bin/activate
python3 agentmain.py
```

确认都能正常读取 `mykey.py`、枚举模型，再去验证 GUI：

```bash
python3 launch.pyw
```

## compare_lab 与浏览器桥

### 历史实验产物

解包后，以下历史回放应当直接可用：

```text
compare_lab/runs/
compare_lab/web/runs/
```

例如：

```text
compare_lab/runs/gomoku-final-002/web/index.html
```

### Chrome 路径

在 macOS 上，`web-live` 和浏览器桥实验建议显式指定 Chrome：

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
python -m compare_lab web-live \
  --run-id web-live-smoke-mac-001 \
  --llm-no 1 \
  --duration-minutes 10 \
  --port 8766 \
  --browser-bin "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

### 不建议直接迁移 Chrome profile

不要把 Linux 上运行中的 Chrome 用户目录当作“登录态”直接迁到 Mac。跨操作系统的浏览器 profile 不稳定，也不作为迁移目标。

## macOS `.app` 启动器

仓库里现成有：

```text
GenericAgent/assets/install-macos-app.sh
GenericAgent_LDY/assets/install-macos-app.sh
```

但两份脚本当前都写死了：

```bash
APP_NAME="GenericAgent"
```

所以如果你同时安装两份 `.app`，它们会互相覆盖。

推荐顺序：

1. 先确认 CLI 和 `launch.pyw` 跑通
2. 再单独改 installer，把 LDY 那份改成 `GenericAgent_LDY.app`
3. 最后再安装桌面 app

## 建议的迁移顺序

1. Linux 上提交当前源码状态并合并到 `main`
2. 运行 `scripts/export_mac_research_bundle.sh`
3. Mac 上 clone 仓库
4. Mac 上建 `.venv` 并安装基础依赖
5. 解包本地研究状态 bundle
6. 验证 `GenericAgent` / `GenericAgent_LDY` CLI
7. 验证 `compare_lab` 历史回放
8. 最后验证浏览器桥和 `web-live`

