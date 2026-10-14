"""
训练冒烟测试（L4，只在训练环境里运行：bash tools/run_tests.sh train）。

用合成的小数据集走一遍练习 3 的后半程：预标注 -> 按场次组装 -> 从网络结构（yolo26n.yaml）
训练 1 轮 -> 评估 -> 导出 opset 18 的 ONNX -> 用 ROS 节点同一套代码加载并推理。
不下载预训练权重，也不追求精度：只检查每一步都能跑通、产物的格式对。
"""
import importlib.util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.train, pytest.mark.slow, pytest.mark.timeout(900),
              pytest.mark.skipif(importlib.util.find_spec('ultralytics') is None,
                                 reason='需要训练环境：conda activate hci-train'),
              # Ultralytics 导出 ONNX 时，PyTorch 提示它用的是旧版导出器：不影响结果，不显示
              pytest.mark.filterwarnings('ignore:You are using the legacy TorchScript-based ONNX'),
              pytest.mark.filterwarnings('ignore:The feature will be removed'),
              pytest.mark.filterwarnings('ignore:Converting a tensor to a Python boolean')]


@pytest.fixture(scope='module')
def trained(tmp_path_factory):
    """合成数据集训练 1 轮，返回 (数据文件夹, 数据集, best.pt)。"""
    from build_dataset import split, write
    from prelabel_yunet import prelabel
    from synthetic import write_faces
    from train import train

    root = tmp_path_factory.mktemp('smoke')
    data = root / 'data'
    for session in ('s1', 's2'):
        write_faces(data / 'self' / session, n=6, prefix=session)
    write_faces(data / 'others' / 'images', n=6, prefix='other', flip=True, scale=0.8)
    assert prelabel(data / 'self', 0, data, largest_only=True).boxes == 12
    assert prelabel(data / 'others' / 'images', 1, data).boxes == 6
    items, _ = split(data)
    write(items, root / 'dataset', '2023123456')
    best = train(str(root / 'dataset' / 'data.yaml'), model='yolo26n.yaml', epochs=1,
                 imgsz=160, batch=4, workers=0, project=root / 'runs', name='smoke', plots=False)
    return data, root / 'dataset', best


def test_training_writes_the_best_weights(trained):
    _, _, best = trained
    assert best.name == 'best.pt' and best.is_file()


def test_evaluate_reports_metrics_and_folder_counts(trained, tmp_path):
    from evaluate import check_folder, validate
    data, dataset, best = trained
    from ultralytics import YOLO
    model = YOLO(str(best))
    metrics = validate(model, str(dataset / 'data.yaml'), imgsz=160, project=tmp_path, plots=False)
    assert {'map50', 'map', 'per_class'} <= set(metrics) and 0.0 <= metrics['map50'] <= 1.0
    counts = check_folder(model, data / 'self' / 's2', imgsz=160, conf=0.01)
    assert sum(counts.values()) == 6  # 每张图都归入"本人、他人、没检测到"之一


def test_export_opset_18_loads_with_the_node_code(trained):
    import onnx
    from export_onnx import compare, export
    from hci_perception.recognition.yolo_onnx import OnnxYolo
    data, _, best = trained
    path = export(str(best), imgsz=160, opset=18)
    assert path.suffix == '.onnx' and path.is_file()
    assert {op.version for op in onnx.load(str(path)).opset_import if op.domain == ''} == {18}
    model = OnnxYolo(str(path), min_confidence=0.01)
    assert model.imgsz == 160 and model.names == ['stu_2023123456', 'face']
    images = sorted((data / 'self' / 's2').glob('*.jpg'))
    result = compare(str(best), str(path), images, imgsz=160)
    assert result.images == 6 and result.pt_ms > 0 and result.onnx_ms > 0


def test_predict_with_the_exported_model(trained, tmp_path):
    from predict import predict
    data, _, best = trained
    onnx_path = Path(best).with_suffix('.onnx')
    if not onnx_path.exists():
        from export_onnx import export
        onnx_path = export(str(best), imgsz=160, opset=18)
    counts = predict(str(onnx_path), str(data / 'self' / 's1'), save=tmp_path / 'out', show=False)
    assert counts['images'] == 6 and len(list((tmp_path / 'out').iterdir())) == 6
