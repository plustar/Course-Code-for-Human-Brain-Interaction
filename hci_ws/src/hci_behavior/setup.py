from setuptools import find_packages, setup

package_name = 'hci_behavior'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    package_data={'': ['py.typed']},
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HCI Course',
    maintainer_email='hci-course@example.com',
    description='人机交互工程课程的行为包：估计目标、状态机决策、安全检查，控制机器人转向、靠近与问候',
    license='AGPL-3.0-only',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'behavior_node = hci_behavior.ros.behavior_node:main',
        ],
    },
)
