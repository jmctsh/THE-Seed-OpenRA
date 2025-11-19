#!/usr/bin/env bash

VENV_DIR=".venv"

# 1. venv 不存在 → 自动创建
if [ ! -d "$VENV_DIR" ]; then
  echo "🌱 Creating virtual environment..."
  python3 -m venv $VENV_DIR
fi

# 2. 激活 venv
source $VENV_DIR/bin/activate

# 3. 安装本地 the-seed（只安装一次，不重复）
if ! pip show the-seed >/dev/null 2>&1; then
  echo "📦 Installing the-seed into venv..."
  pip install -e ./the-seed
fi

# 4. 安装依赖
pip install -r requirements.txt

# 5. 运行
python run.py