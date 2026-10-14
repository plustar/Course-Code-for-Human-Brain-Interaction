from setuptools import find_packages, setup

package_name = 'hci_common'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    package_data={'': ['py.typed'], package_name: ['data/*']},
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HCI Course',
    maintainer_email='hci-course@example.com',
    description='人机交互工程课程的地基包：相机模型、参数声明、节点运行、图像消息转换、测试辅助',
    license='AGPL-3.0-only',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [],
    },
)
