# 维护说明

写给助教和课程维护者：怎样发布新版本、学期中怎样更新、每学期开始前要检查什么。学生不需要读这份文件。

## 1. 版本号

版本号的格式是 `主.次.修订`，写在 11 个地方：6 个包的 `package.xml`（`<version>`）和 5 个 Python 包的 `setup.py`（`version=`；`hci_interfaces` 是 CMake 包，没有 setup.py）。`tests/test_repo_hygiene.py` 检查它们一致。

学生运行 `bash env/check_env.sh` 时，第一行显示这个版本号；用 git clone 得到的仓库，还显示 git 的描述，例如 `v1.0.1-3-gabc1234-dirty`：标签 v1.0.1 之后又有 3 个提交，本地还有没提交的改动。学生提问时附上这一行（README 第 11 节），就知道他用的是哪一版。

| 改动 | 版本号 | 例子 |
|---|---|---|
| 修复问题、改文档，用法不变 | 修订号加 1 | 1.0.0 → 1.0.1 |
| 新增功能，或者改了参数名、话题名、脚本的用法 | 次版本号加 1 | 1.0.1 → 1.1.0 |
| 换 Ubuntu 或 ROS 2 的版本 | 主版本号加 1 | 1.1.0 → 2.0.0 |

一次改完 11 处，再检查：

```bash
cd $HCI_ROOT
NEW=1.0.1
sed -i "s#<version>.*</version>#<version>$NEW</version>#" hci_ws/src/*/package.xml
sed -i "s#version='[^']*'#version='$NEW'#" hci_ws/src/*/setup.py
python3 -m pytest -q tests/test_repo_hygiene.py
```

## 2. 发布

提交和标签会公开显示作者的姓名和邮箱。第一次提交之前，在仓库里设置课程统一的身份（只对这个仓库生效），不要用自己的私人邮箱：

```bash
cd $HCI_ROOT
git config user.name "HCI Course"
git config user.email hci-course@example.com
```

在 GitHub 网页上合并 Pull Request 时，用的是网页账号的邮箱：在 GitHub 的 Settings → Emails 里勾选 Keep my email addresses private。

第一次推送到 GitHub 之后，给当时的提交打上 `v1.0.0` 标签（下面第 3 步）。以后每次发布：

1. 两个环境的测试都通过：`bash tools/run_tests.sh --gui`；`conda activate hci-train && bash tools/run_tests.sh train`。GitHub 的 Actions 页面也是绿色的。
2. 改版本号（第 1 节），在 `docs/VERIFICATION.md` 里记下这次验证的环境和结果。
3. 提交、打标签、推送：
   ```bash
   git commit -am "Release 2.0.1: 一句话说明"
   git tag -a v2.0.1 -m "改了什么"
   git push origin main v2.0.1
   ```
4. 在 GitHub 的 Releases 页面用这个标签发布，写明改了什么、学生要做什么（第 3 节）。
5. 在课程群里通知。

## 3. 学期中更新：告诉学生怎么做

学生自己的数据都在仓库文件夹里（`exercises/face_recognition/` 下的 `data/`、`dataset/`、`runs/`、`out/`），被 `.gitignore` 排除。更新代码时要保留它们：

- **用 git clone 的**：`cd $HCI_ROOT && git pull`，再 `cd hci_ws && colcon build --symlink-install`。git 不会动被忽略的文件。提示本地有改动（学生改过参考代码）时，先 `git stash`，pull 之后再 `git stash pop`。
- **下载 ZIP 的**：把旧文件夹改名为 `hci-course-code-old`，新 ZIP 解压后改名为 `hci-course-code`；把上面四个文件夹（和自己改过的文件）从旧文件夹移过来；在新文件夹的 `hci_ws` 里重新编译。确认一切正常后再删除旧文件夹。

改了 `env/` 里的脚本或依赖时，还要请学生重新运行对应的脚本：`bash env/setup_ros_env.sh`，或者 `bash env/setup_conda.sh`。两个脚本重复运行都是安全的，已经装好的部分会跳过。

## 4. 每学期开始前

1. **在干净的系统上装一遍。** 新装一个 Ubuntu 26.04（WSL2 最方便：`wsl --install -d Ubuntu-26.04`，用完 `wsl --unregister Ubuntu-26.04`），严格按 README 第 4 节安装，跑 `bash tools/run_tests.sh --gui` 和训练环境的测试，再把练习 3 从录制到导出完整走一遍。ROS 环境的包来自 apt，会随系统更新，所以每学期都要重新验证。
2. **训练环境的版本锁定。** 训练用的包锁定在实测过的小版本，学期中上游发布新版本也不影响学生：

   | 包 | 锁定在 | 写在 |
   |---|---|---|
   | torch、torchvision | 2.14.x、0.29.x | `env/setup_conda.sh` |
   | ultralytics | 8.4.x | `env/requirements-train.txt` |
   | onnx、onnxslim、onnxruntime | 1.23.x、0.1.x、1.30.x | `env/requirements-train.txt` |

   要升级时，一次只放宽一个包，在新建的环境里重跑训练环境的测试和练习 3 的完整流程。重点确认导出的 ONNX 能被 ROS 环境的 onnxruntime（apt 安装）加载：`bash tools/run_tests.sh` 的 L3 会检查。都通过后，再更新锁定的版本、`tests/test_env_scripts.py` 里对应的检查和 README 第 4.4 节的说明。
3. **GitHub Actions 的定时运行。** 公开仓库 60 天没有新的提交时，GitHub 会自动停用定时运行（`train.yml` 每周一次）。到仓库的 Actions 页面选中 train，点 Enable workflow，再点 Run workflow 手动跑一次。
4. **模型的下载地址。** `tools/download_models.sh` 从 OpenCV Zoo 下载 SFace，并校验 SHA256。上游地址失效时，只改脚本里的地址，SHA256 不变。
5. **记录。** 在 `docs/VERIFICATION.md` 里记下环境（Ubuntu、ROS、主要 Python 包的版本）和结果。

## 5. GitHub 仓库的设置

- **关闭 Issues**（Settings → General → Features，取消勾选 Issues）。学生的问题统一在课程群里问或者找助教（README 第 11 节），免得有人在公开页面贴出带人脸的截图或学号。
- Pull Request 可以保留。合并前确认没有个人数据：`tests/test_repo_hygiene.py` 会在 CI 里检查。
- 两个工作流只申请了读取代码的权限（`permissions: contents: read`），不需要另外改仓库的 Actions 设置。

## 6. 发布前的隐私检查

随仓库发布的照片和模型只有两个，`git ls-files` 里不应该出现别的照片、视频、权重、人脸特征或录包：

```bash
git ls-files | grep -iE '\.(jpe?g|png|heic|heif|webp|bmp|tiff?|gif|avif|mp4|m4v|mov|avi|mkv|wmv|webm|3gp|npy|pt|pth|onnx|zip|7z|rar|tar|tgz|gz|mcap|db3)$'
# 只应列出这两个：
#   hci_ws/src/hci_common/hci_common/data/sample_face.jpg                               NASA 公有领域照片
#   hci_ws/src/hci_perception/hci_perception/models/face_detection_yunet_2023mar.onnx    MIT 许可
```

`package.xml` 和 `setup.py` 里的维护者邮箱一律用占位地址 `hci-course@example.com`，`tests/test_repo_hygiene.py` 会检查；提交和标签里的邮箱测试查不到，按第 2 节设置。第三方文件的许可全文放在 `LICENSES/` 和模型旁边（README 第 13 节），新增第三方文件时一并补上。
