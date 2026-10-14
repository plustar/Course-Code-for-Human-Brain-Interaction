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
# 另一处改动：xmllint 要联网下载 package.xml 引用的 XSD，下载不到（或下载中途卡住、中断）时
# 跳过并说明原因，而不是报一个与代码无关的失败。

from pathlib import Path
import socket
import urllib.request

from ament_xmllint.main import main
import pytest

PACKAGE = str(Path(__file__).resolve().parents[1])  # 本测试所在的包
SCHEMA = 'http://download.ros.org/schema/package_format3.xsd'


def schema_reachable() -> bool:
    try:
        urllib.request.urlopen(SCHEMA, timeout=10).close()
        return True
    except OSError:
        return False


@pytest.mark.linter
@pytest.mark.xmllint
def test_xmllint(capsys: pytest.CaptureFixture[str]) -> None:
    if not schema_reachable():
        pytest.skip(f'下载不到 {SCHEMA}（离线或网络受限），联网后再检查 package.xml')
    # ament_xmllint 下载 XSD 时不设超时，网络时断时续会一直卡住：限定 20 秒
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(20)
    try:
        rc = main(argv=[PACKAGE])
    finally:
        socket.setdefaulttimeout(old_timeout)
    output = capsys.readouterr()
    if rc != 0 and 'failed to download schema' in output.err:
        pytest.skip(f'下载 {SCHEMA} 时网络中断或超时，联网后再检查 package.xml')
    assert rc == 0, 'Found code style errors / warnings\n' + output.out + output.err
