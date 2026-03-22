"""
full_navigation_g1.launch.py — Complete navigation pipeline for Unitree G1.

Combines:
  1. FAST-LIO odometry (camera_init → imu_link TF, /Odometry_loc)
  2. Open3D global localization (map → odom TF)
  3. Nav2 navigation stack (path planning, control, costmaps)
  4. Optional: pointcloud_to_laserscan for 2D scan visualization
  5. RViz2

Usage:
  ros2 launch nav2_humanoid full_navigation_g1.launch.py
  ros2 launch nav2_humanoid full_navigation_g1.launch.py use_sim_time:=true
"""
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    GroupAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    fast_lio_share = FindPackageShare('fast_lio')
    open3d_loc_share = FindPackageShare('open3d_loc')
    nav2_bringup_share = FindPackageShare('nav2_bringup')
    nav2_humanoid_share = FindPackageShare('nav2_humanoid')

    # ---- Launch arguments -----------------------------------
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time', default_value='false')

    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=PathJoinSubstitution([
            nav2_humanoid_share, 'config', 'nav2_params_g1.yaml'
        ]))

    enable_rviz_arg = DeclareLaunchArgument(
        'rviz', default_value='true',
        description='Launch RViz2')

    enable_pc2ls_arg = DeclareLaunchArgument(
        'enable_pointcloud_to_laserscan', default_value='false',
        description='Enable pointcloud_to_laserscan node for 2D scan')

    # ---- 1. FAST-LIO odometry ------------------------------
    fast_lio_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                fast_lio_share, 'launch', 'mapping.launch.py'
            ])
        ]),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }.items()
    )

    # ---- 2. Open3D global localization ----------------------
    open3d_loc_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                open3d_loc_share, 'launch', 'open3d_loc_g1.launch.py'
            ])
        ]),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }.items()
    )

    # ---- 3. Nav2 navigation stack ---------------------------
    nav2_navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                nav2_bringup_share, 'launch', 'navigation_launch.py'
            ])
        ]),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'params_file': LaunchConfiguration('params_file'),
            'autostart': 'true',
        }.items()
    )

    # ---- 4. Optional: pointcloud → 2D laser scan -----------
    pc2ls_node = GroupAction(
        condition=IfCondition(
            LaunchConfiguration('enable_pointcloud_to_laserscan')),
        actions=[
            Node(
                package='pointcloud_to_laserscan',
                executable='pointcloud_to_laserscan_node',
                name='pointcloud_to_laserscan',
                parameters=[{
                    'target_frame': 'base_link',
                    'transform_tolerance': 0.01,
                    'min_height': 0.05,
                    'max_height': 1.5,
                    'angle_min': -3.14159,
                    'angle_max': 3.14159,
                    'angle_increment': 0.00872,  # ~0.5 deg
                    'scan_time': 0.1,
                    'range_min': 0.3,
                    'range_max': 15.0,
                    'use_inf': True,
                    'inf_epsilon': 1.0,
                    'use_sim_time':
                        LaunchConfiguration('use_sim_time'),
                }],
                remappings=[
                    ('cloud_in', '/cloud_registered_body_1'),
                    ('scan', '/scan'),
                ],
            ),
        ]
    )

    # ---- 5. RViz2 ------------------------------------------
    rviz_config_path = PathJoinSubstitution([
        nav2_humanoid_share, 'config', 'nav2_default_view.rviz'
    ])

    rviz_node = GroupAction(
        condition=IfCondition(LaunchConfiguration('rviz')),
        actions=[
            Node(
                package='rviz2',
                executable='rviz2',
                name='rviz2_nav',
                arguments=['-d', rviz_config_path],
                output='screen',
                prefix='nice',
            ),
        ]
    )

    return LaunchDescription([
        use_sim_time_arg,
        params_file_arg,
        enable_rviz_arg,
        enable_pc2ls_arg,
        fast_lio_launch,
        open3d_loc_launch,
        nav2_navigation,
        pc2ls_node,
        rviz_node,
    ])
