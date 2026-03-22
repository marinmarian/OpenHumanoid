"""
nav2_g1.launch.py — Launch Nav2 navigation stack for Unitree G1.

This starts ONLY the navigation stack (no localization).
Localization must be running separately via localization_3d_g1.launch.py
which publishes the map→odom TF via Open3D ICP.

Usage:
  ros2 launch nav2_humanoid nav2_g1.launch.py
  ros2 launch nav2_humanoid nav2_g1.launch.py use_sim_time:=true
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    nav2_bringup_share = FindPackageShare('nav2_bringup')
    nav2_humanoid_share = FindPackageShare('nav2_humanoid')

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation time'
    )

    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=PathJoinSubstitution([
            nav2_humanoid_share, 'config', 'nav2_params_g1.yaml'
        ]),
        description='Path to Nav2 parameters YAML file'
    )

    autostart_arg = DeclareLaunchArgument(
        'autostart',
        default_value='true',
        description='Automatically start Nav2 lifecycle nodes'
    )

    # Use nav2_bringup's navigation_launch.py which starts:
    #   controller_server, planner_server, smoother_server,
    #   behavior_server, bt_navigator, waypoint_follower,
    #   velocity_smoother, lifecycle_manager_navigation
    nav2_navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                nav2_bringup_share, 'launch', 'navigation_launch.py'
            ])
        ]),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'params_file': LaunchConfiguration('params_file'),
            'autostart': LaunchConfiguration('autostart'),
        }.items()
    )

    return LaunchDescription([
        use_sim_time_arg,
        params_file_arg,
        autostart_arg,
        nav2_navigation,
    ])
