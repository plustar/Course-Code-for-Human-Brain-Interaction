from setuptools import find_packages, setup

package_name = 'hci_perception'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    package_data={'': ['py.typed'],
                  package_name: ['models/*.onnx', 'models/*.md', 'models/*.txt']},
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HCI Course',
    maintainer_email='hci-course@example.com',
    description='人机交互工程课程的感知包：摄像头、人脸识别（YOLO / YuNet / 两步法）与显示',
    license='AGPL-3.0-only',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            # 可执行文件名 = 模块:函数
            'camera_node = hci_perception.ros.camera_node:main',
            'recognizer_node = hci_perception.ros.recognizer_node:main',
            'viewer_node = hci_perception.ros.viewer_node:main',
        ],
    },
)
