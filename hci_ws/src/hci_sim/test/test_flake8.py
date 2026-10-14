# Copyright 2017 Open Source Robotics Foundation, Inc.
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

from pathlib import Path

from ament_flake8.main import main_with_errors
import pytest

PACKAGE = str(Path(__file__).resolve().parents[1])  # 本测试所在的包


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8() -> None:
    rc, errors = main_with_errors(argv=[PACKAGE])
    assert rc == 0, \
        'Found %d code style errors / warnings:\n' % len(errors) + \
        '\n'.join(errors)
