# Copyright 2015 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# 本文件改自 ros2pkg 的 ament_python 包模板（Lyrical）。改动：检查本文件所在的整个包，
# 与当前目录无关，所以在仓库根目录直接运行 pytest 也能得到同样的结果。
# 另一处改动：忽略三条只适用于英文的规则。D400、D415 要求第一行以英文句点结尾，
# D403 要求第一个英文单词首字母大写；本课程的文档字符串用中文写，以"。"结尾，
# 常以 YuNet、turtlesim 这样的专名开头。

from pathlib import Path

from ament_pep257.main import main
import pytest

PACKAGE = str(Path(__file__).resolve().parents[1])  # 本测试所在的包


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257() -> None:
    rc = main(argv=[PACKAGE, '--add-ignore', 'D400', 'D403', 'D415'])
    assert rc == 0, 'Found code style errors / warnings'
