#!/usr/bin/env bash
# Test script to verify backend can start with proper configuration

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Check if API key is set
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "❌ DEEPSEEK_API_KEY is not set"
  echo ""
  echo "Please set your DeepSeek API key:"
  echo "  export DEEPSEEK_API_KEY='your-api-key-here'"
  echo ""
  echo "Or if you're using OpenAI:"
  echo "  export OPENAI_API_KEY='your-api-key-here'"
  echo "  And update the-seed/the_seed/config/schema.py base_url to https://api.openai.com/v1"
  exit 1
fi

echo "✓ DEEPSEEK_API_KEY is set"
echo ""

# Test configuration loading
echo "📋 Testing configuration..."
python3 -c "
from the_seed.config.manager import load_config
cfg = load_config()
print(f'  base_url: {cfg.model_templates[\"default\"].base_url}')
print(f'  model: {cfg.model_templates[\"default\"].model}')
print(f'  api_key: {cfg.model_templates[\"default\"].api_key[:10]}...')
"

if [ $? -ne 0 ]; then
  echo "❌ Configuration test failed"
  exit 1
fi

echo "✓ Configuration loaded successfully"
echo ""

# Test imports
echo "📦 Testing imports..."
python3 -c "
from the_seed.core.factory import NodeFactory
from the_seed.core.fsm import FSM, FSMContext
from the_seed.utils import DashboardBridge
print('✓ All imports successful')
"

if [ $? -ne 0 ]; then
  echo "❌ Import test failed"
  exit 1
fi

echo ""
echo "✅ Backend is ready to run!"
echo ""
echo "Next steps:"
echo "  1. Make sure OpenRA is running on localhost:7445"
echo "  2. Run: ./run.sh"
echo "  3. Dashboard will open automatically"
echo "  4. Try command: 展开基地车"
