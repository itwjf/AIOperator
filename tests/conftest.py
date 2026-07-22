"""pytest 全局配置与 fixtures。"""

import sys
from pathlib import Path

# 确保能 import app 包（项目根目录加入 sys.path）
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
