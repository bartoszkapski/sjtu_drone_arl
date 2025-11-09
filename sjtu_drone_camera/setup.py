from setuptools import find_packages, setup

package_name = 'sjtu_drone_camera'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=[
        'setuptools',
        'ultralytics==8.3.25',        
    ],
    zip_safe=True,
    maintainer='fhtw_user',
    maintainer_email='fhtw_user@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'image_saver = sjtu_drone_camera.image_saver:main',
            'detect_object_by_yolo = sjtu_drone_camera.detect_object_by_yolo:main',
        ],
    },
)
