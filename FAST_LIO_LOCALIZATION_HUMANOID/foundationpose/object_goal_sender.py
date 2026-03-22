#!/usr/bin/env python3
"""
object_goal_sender.py — Bridge between FoundationPoseROS2 detections and Nav2.

Subscribes to object pose topics published by FoundationPoseROS2
(/Current_OBJ_position_*) and converts them into Nav2 navigation goals.

Modes:
  - "navigate": Send the robot to a standoff position near the detected object
  - "track":    Continuously update the goal as the object moves
  - "once":     Navigate to the first detection, then stop

The node transforms object poses from the camera frame into the map frame
before sending them as Nav2 goals.

Usage:
  ros2 run nav2_humanoid object_goal_sender --ros-args \
      -p mode:=navigate -p standoff_distance:=0.5 -p object_id:=1
"""
import math
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.duration import Duration

from geometry_msgs.msg import PoseStamped, TransformStamped
from nav2_msgs.action import NavigateToPose
from tf2_ros import Buffer, TransformListener, TransformException
import tf2_geometry_msgs  # noqa: F401  — registers PoseStamped transform


class ObjectGoalSender(Node):
    def __init__(self):
        super().__init__('object_goal_sender')

        # Parameters
        self.declare_parameter('mode', 'navigate')         # navigate | track | once
        self.declare_parameter('standoff_distance', 0.5)   # metres in front of object
        self.declare_parameter('object_id', 1)              # which object to follow
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('min_goal_change', 0.3)      # metres — suppress jitter

        self.mode = self.get_parameter('mode').value
        self.standoff = self.get_parameter('standoff_distance').value
        self.object_id = self.get_parameter('object_id').value
        self.map_frame = self.get_parameter('map_frame').value
        self.min_goal_change = self.get_parameter('min_goal_change').value

        # TF2
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # Nav2 action client
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # Subscribe to the object pose topic from FoundationPoseROS2
        topic = f'/Current_OBJ_position_{self.object_id}'
        self.subscription = self.create_subscription(
            PoseStamped, topic, self.object_pose_callback, 10)
        self.get_logger().info(
            f'Listening on {topic} | mode={self.mode} | standoff={self.standoff}m')

        self.last_goal = None
        self.goal_sent = False
        self.current_goal_handle = None

    def object_pose_callback(self, msg: PoseStamped):
        """Called when FoundationPoseROS2 publishes an object pose."""
        if self.mode == 'once' and self.goal_sent:
            return

        # Transform object pose into map frame
        try:
            map_pose = self.tf_buffer.transform(
                msg, self.map_frame, timeout=Duration(seconds=0.5))
        except TransformException as e:
            self.get_logger().warn(f'TF transform failed: {e}')
            return

        # Compute standoff goal — position the robot `standoff` metres
        # in front of the object, facing toward it.
        goal_pose = self._compute_standoff_goal(map_pose)

        # Suppress jitter — only send if the goal moved significantly
        if self.last_goal is not None:
            dx = goal_pose.pose.position.x - self.last_goal.pose.position.x
            dy = goal_pose.pose.position.y - self.last_goal.pose.position.y
            if math.hypot(dx, dy) < self.min_goal_change:
                return

        self.last_goal = goal_pose
        self._send_goal(goal_pose)

    def _compute_standoff_goal(self, object_pose: PoseStamped) -> PoseStamped:
        """Place the robot standoff_distance away from the object, facing it."""
        obj_x = object_pose.pose.position.x
        obj_y = object_pose.pose.position.y

        # Robot's current position (for approach direction)
        try:
            t = self.tf_buffer.lookup_transform(
                self.map_frame, 'base_link', rclpy.time.Time(),
                timeout=Duration(seconds=0.5))
            robot_x = t.transform.translation.x
            robot_y = t.transform.translation.y
        except TransformException:
            # Fallback: approach from current yaw = 0 direction
            robot_x = obj_x - self.standoff
            robot_y = obj_y

        # Direction from object to robot (we want to stop along this line)
        dx = robot_x - obj_x
        dy = robot_y - obj_y
        dist = math.hypot(dx, dy)
        if dist < 0.01:
            dx, dy = 1.0, 0.0
            dist = 1.0

        # Standoff point along object→robot direction
        goal_x = obj_x + (dx / dist) * self.standoff
        goal_y = obj_y + (dy / dist) * self.standoff

        # Face toward the object
        yaw = math.atan2(obj_y - goal_y, obj_x - goal_x)

        goal = PoseStamped()
        goal.header.frame_id = self.map_frame
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = goal_x
        goal.pose.position.y = goal_y
        goal.pose.position.z = 0.0
        goal.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.orientation.w = math.cos(yaw / 2.0)

        self.get_logger().info(
            f'Object at ({obj_x:.2f}, {obj_y:.2f}) → '
            f'Goal at ({goal_x:.2f}, {goal_y:.2f}), yaw={math.degrees(yaw):.0f}°')
        return goal

    def _send_goal(self, goal_pose: PoseStamped):
        """Send navigation goal to Nav2."""
        if not self.nav_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().error('Nav2 navigate_to_pose action server not available')
            return

        # Cancel previous goal in track mode
        if self.mode == 'track' and self.current_goal_handle is not None:
            self.get_logger().info('Cancelling previous goal (track mode)')
            self.current_goal_handle.cancel_goal_async()

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = goal_pose

        self.get_logger().info(
            f'Sending Nav2 goal → ({goal_pose.pose.position.x:.2f}, '
            f'{goal_pose.pose.position.y:.2f})')

        future = self.nav_client.send_goal_async(
            goal_msg, feedback_callback=self._feedback_callback)
        future.add_done_callback(self._goal_response_callback)

    def _goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('Nav2 goal rejected')
            return

        self.get_logger().info('Nav2 goal accepted')
        self.current_goal_handle = goal_handle
        self.goal_sent = True

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._result_callback)

    def _result_callback(self, future):
        result = future.result()
        self.get_logger().info(f'Navigation result: {result.status}')
        self.current_goal_handle = None

    def _feedback_callback(self, feedback_msg):
        remaining = feedback_msg.feedback.distance_remaining
        if remaining > 0:
            self.get_logger().info(
                f'Distance remaining: {remaining:.2f}m', throttle_duration_sec=2.0)


def main(args=None):
    rclpy.init(args=args)
    node = ObjectGoalSender()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
