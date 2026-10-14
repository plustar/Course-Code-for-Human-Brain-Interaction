from setuptools import find_packages, setup

package_name = 'hci_sim'

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
    description='人机交互工程课程的轻量仿真器：turtlesim 里的虚拟人与装在机器人上的虚拟相机',
    license='AGPL-3.0-only',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'virtual_camera_node = hci_sim.ros.virtual_camera_node:main',
        ],
    },
)
