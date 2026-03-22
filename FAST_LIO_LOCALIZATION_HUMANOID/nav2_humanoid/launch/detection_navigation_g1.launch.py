"""
detection_navigation_g1.launch.py — Full pipeline with object detection.

Combines:
  1. FAST-LIO odometry
  2. Open3D global localization
  3. Nav2 navigation stack
  4. RealSense camera driver
  5. Object goal sender (bridge: detections → Nav2 goals)
  6. RViz2

FoundationPoseROS2 runs in a separate container (needs GPU).
This launch file starts everything EXCEPT FoundationPoseROS2 itself.

Usage:
  ros2 launch nav2_humanoid detection_navigation_g1.launch.py
  ros2 launch nav2_humanoid detection_navigation_g1.launch.py object_id:=2
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

    enable_realsense_arg = DeclareLaunchArgument(
        'enable_realsense', default_value='true',
        description='Launch RealSense camera driver')

    enable_goal_sender_arg = DeclareLaunchArgument(
        'enable_goal_sender', default_value='true',
        description='Launch object_goal_sender bridge node')

    mode_arg = DeclareLaunchArgument(
        'mode', default_value='navigate',
        description='Goal sender mode: navigate | track | once')

    standoff_arg = DeclareLaunchArgument(
        'standoff_distance', default_value='0.5',
        description='Distance to stop from detected object (metres)')

    object_id_arg = DeclareLaunchArgument(
        'object_id', default_value='1',
        description='Which FoundationPose object ID to navigate to')

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

    # ---- 4. RealSense camera (RGB-D for FoundationPose) -----
    realsense_node = GroupAction(
        condition=IfCondition(LaunchConfiguration('enable_realsense')),
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([
                    PathJoinSubstitution([
                        FindPackageShare('realsense2_camera'),
                        'launch', 'rs_launch.py'
                    ])
                ]),
                launch_arguments={
                    'enable_rgbd': 'true',
                    'enable_sync': 'true',
                    'align_depth.enable': 'true',
                    'enable_color': 'true',
                    'enable_depth': 'true',
                    'pointcloud.enable': 'true',
                }.items()
            ),
        ]
    )

    # ---- 5. Object goal sender (detection → Nav2) -----------
    goal_sender_node = GroupAction(
        condition=IfCondition(LaunchConfiguration('enable_goal_sender')),
        actions=[
            Node(
                package='nav2_humanoid',
                executable='object_goal_sender',
                name='object_goal_sender',
                parameters=[{
                    'mode': LaunchConfiguration('mode'),
                    'standoff_distance':
                        LaunchConfiguration('standoff_distance'),
                    'object_id': LaunchConfiguration('object_id'),
                    'map_frame': 'map',
                    'min_goal_change': 0.3,
                    'use_sim_time':
                        LaunchConfiguration('use_sim_time'),
                }],
                output='screen',
            ),
        ]
    )

    # ---- 6. RViz2 ------------------------------------------
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
        enable_realsense_arg,
        enable_goal_sender_arg,
        mode_arg,
        standoff_arg,
        object_id_arg,
        fast_lio_launch,
        open3d_loc_launch,
        nav2_navigation,
        realsense_node,
        goal_sender_node,
        rviz_node,
    ])
