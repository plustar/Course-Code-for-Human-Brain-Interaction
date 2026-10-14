"""练习 3 测试的公共设置：脚本放在上一级目录，把它加进导入路径。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
