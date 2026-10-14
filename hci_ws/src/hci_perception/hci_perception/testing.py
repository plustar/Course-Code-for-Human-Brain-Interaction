"""
测试用的辅助工具（只在测试里用）：生成微型的"YOLO"ONNX 模型。

微型模型不管输入什么，都输出给定的张量 raw，用来测试 ONNX 后端的整条链路
（letterbox -> 推理 -> 解码 -> 坐标还原），不需要训练。感知包的测试和练习 3 的测试都用它。

模型在子进程里用 onnx 包生成：Ubuntu 26.04 用 apt 安装的 onnx 与 onnxruntime 不能在同一个
进程里导入（两者注册同一份 protobuf 描述，进程会直接崩溃）；用 pip 安装的训练环境没有这个问题。
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Optional, Sequence

import numpy as np

MAKE_MODEL = textwrap.dedent("""
    import json
    import sys

    import numpy as np
    import onnx
    from onnx import helper, numpy_helper, TensorProto

    path, raw_path, size, names = sys.argv[1], sys.argv[2], *map(json.loads, sys.argv[3:5])
    raw = np.load(raw_path).astype(np.float32)
    dims = [1, 3, size, size] if size else ['batch', 3, 'height', 'width']
    graph = helper.make_graph(
        [helper.make_node('ReduceMean', ['images'], ['mean'], keepdims=0),
         helper.make_node('Mul', ['mean', 'zero'], ['nothing']),  # 让输出"依赖"输入
         helper.make_node('Add', ['raw', 'nothing'], ['output0'])],
        'tiny_yolo',
        [helper.make_tensor_value_info('images', TensorProto.FLOAT, dims)],
        [helper.make_tensor_value_info('output0', TensorProto.FLOAT, list(raw.shape))],
        initializer=[numpy_helper.from_array(raw, 'raw'),
                     numpy_helper.from_array(np.zeros((), np.float32), 'zero')])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 18)])
    model.ir_version = 9
    if names:
        model.metadata_props.add(key='names', value=str(dict(enumerate(names))))
    onnx.checker.check_model(model)
    onnx.save(model, path)
""")


def onnx_available() -> bool:
    """能不能生成微型模型（需要 onnx 包：ROS 环境 python3-onnx，训练环境自带）。"""
    return importlib.util.find_spec('onnx') is not None


def make_tiny_yolo(path: Path, raw: np.ndarray, size: Optional[int] = 320,
                   names: Optional[Sequence[str]] = None) -> Path:
    """
    在 path 生成微型模型，返回 path。

    raw：模型的输出，例如 (1, 4+类别数, 候选数) 的传统格式或 (1, N, 6) 的端到端格式；
    size 为 None 时输入尺寸是动态的；names 写进元数据，与 Ultralytics 导出的格式相同。
    """
    path = Path(path)
    raw_path = path.with_suffix('.npy')
    np.save(raw_path, raw)
    subprocess.run([sys.executable, '-c', MAKE_MODEL, str(path), str(raw_path),
                    json.dumps(size), json.dumps(list(names or []))], check=True)
    raw_path.unlink()
    return path
