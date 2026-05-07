#!/usr/bin/env python3
"""
ball_grasp_node.py
공 잡기 컨트롤 노드 (클래식 파이프라인, ROS2)

[파이프라인]
  /ball/position (PointStamped)  ──┐
                                   ├──► IK ──► JointTrajectory ──► OMX
  /joint_states (JointState)    ──┘                          + 그리퍼

[가정]
- 비전 노드가 base_link 기준 좌표를 PointStamped로 퍼블리시함
- OMX 컨트롤러가 /arm_controller/joint_trajectory 토픽 받음
- 그리퍼는 /gripper_controller/command (Float64) 받음
- 위 토픽명/타입은 ROBOTIS 패키지 보고 맞춰야 함 (TODO 표시)
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PointStamped
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from std_msgs.msg import Float64
import numpy as np
from enum import Enum, auto


# ===== 임의값. 실제 값으로 교체 필요 =====
JOINT_NAMES = ["joint1", "joint2", "joint3", "joint4"]
HOME_POSITION = [0.0, -1.0, 0.5, 0.5]   # rad
APPROACH_OFFSET_Z = 0.10                # m, 공 위 10cm에서 접근
BALL_RADIUS = 0.02                      # m, 탁구공 가정
GRIPPER_OPEN = 0.019                    # m
GRIPPER_CLOSED = 0.005                  # m
MOTION_DURATION = 2.0                   # 초


class State(Enum):
    IDLE = auto()
    APPROACH = auto()    # 공 위쪽으로 이동
    DESCEND = auto()     # 공까지 내려감
    GRASP = auto()       # 그리퍼 닫기
    LIFT = auto()        # 들어올리기
    HOME = auto()        # 복귀
    DONE = auto()


class BallGraspNode(Node):
    def __init__(self):
        super().__init__('ball_grasp_node')

        # ── 입력 ──
        self.create_subscription(
            PointStamped, '/ball/position', self.ball_cb, 10
        )
        self.create_subscription(
            JointState, '/joint_states', self.joint_cb, 10
        )

        # ── 출력 ──
        # TODO: 토픽명 ROBOTIS 패키지 기준으로 확정
        self.traj_pub = self.create_publisher(
            JointTrajectory, '/arm_controller/joint_trajectory', 10
        )
        self.gripper_pub = self.create_publisher(
            Float64, '/gripper_controller/command', 10
        )

        # ── 상태 ──
        self.state = State.IDLE
        self.state_start_time = self.get_clock().now()
        self.ball_xyz = None
        self.current_joints = None

        self.timer = self.create_timer(0.1, self.tick)  # 10Hz
        self.get_logger().info('ball_grasp_node ready.')

    # ===== 콜백 =====
    def ball_cb(self, msg: PointStamped):
        self.ball_xyz = np.array([msg.point.x, msg.point.y, msg.point.z])

    def joint_cb(self, msg: JointState):
        self.current_joints = dict(zip(msg.name, msg.position))

    # ===== IK =====
    def ik(self, target_xyz):
        """
        TODO: OMX 4-DOF 역기구학
          옵션 A) ROBOTIS open_manipulator_x_libs의 IK 함수 사용
          옵션 B) MoveIt2 IK 서비스 호출 (/compute_ik)
          옵션 C) 4-DOF 해석적 IK 직접 구현 (DH 파라미터 필요)
        반환: [j1, j2, j3, j4] (rad)
        """
        x, y, z = target_xyz
        # 더미 — 진짜 IK 들어가야 함
        return [0.0, -0.5, 0.5, 0.0]

    # ===== 송신 헬퍼 =====
    def send_joints(self, joints, duration=MOTION_DURATION):
        traj = JointTrajectory()
        traj.joint_names = JOINT_NAMES
        pt = JointTrajectoryPoint()
        pt.positions = list(joints)
        pt.time_from_start.sec = int(duration)
        pt.time_from_start.nanosec = int((duration % 1) * 1e9)
        traj.points.append(pt)
        self.traj_pub.publish(traj)
        self.get_logger().info(
            f'[CMD] joints={[f"{j:+.2f}" for j in joints]} dur={duration}s'
        )

    def send_gripper(self, position):
        msg = Float64()
        msg.data = float(position)
        self.gripper_pub.publish(msg)
        self.get_logger().info(f'[CMD] gripper={position:.3f}')

    # ===== 상태 전환 =====
    def transition(self, next_state):
        self.get_logger().info(f'{self.state.name} -> {next_state.name}')
        self.state = next_state
        self.state_start_time = self.get_clock().now()

    def elapsed(self):
        return (self.get_clock().now() - self.state_start_time).nanoseconds / 1e9

    # ===== 메인 루프 =====
    def tick(self):
        if self.state == State.IDLE:
            if self.ball_xyz is not None:
                self.transition(State.APPROACH)

        elif self.state == State.APPROACH:
            if self.elapsed() < 0.1:  # 진입 시 1회만 명령
                target = self.ball_xyz + np.array([0, 0, APPROACH_OFFSET_Z])
                self.send_joints(self.ik(target))
                self.send_gripper(GRIPPER_OPEN)
            elif self.motion_done():
                self.transition(State.DESCEND)

        elif self.state == State.DESCEND:
            if self.elapsed() < 0.1:
                target = self.ball_xyz + np.array([0, 0, BALL_RADIUS])
                self.send_joints(self.ik(target))
            elif self.motion_done():
                self.transition(State.GRASP)

        elif self.state == State.GRASP:
            if self.elapsed() < 0.1:
                self.send_gripper(GRIPPER_CLOSED)
            elif self.elapsed() > 1.0:
                self.transition(State.LIFT)

        elif self.state == State.LIFT:
            if self.elapsed() < 0.1:
                target = self.ball_xyz + np.array([0, 0, APPROACH_OFFSET_Z])
                self.send_joints(self.ik(target))
            elif self.motion_done():
                self.transition(State.HOME)

        elif self.state == State.HOME:
            if self.elapsed() < 0.1:
                self.send_joints(HOME_POSITION)
            elif self.motion_done():
                self.transition(State.DONE)

        elif self.state == State.DONE:
            self.get_logger().info('Sequence complete. Resetting.')
            self.ball_xyz = None
            self.transition(State.IDLE)

    def motion_done(self):
        """
        TODO: 진짜 모션 완료 판정으로 교체
          옵션 A) FollowJointTrajectory 액션 클라이언트 결과 확인
          옵션 B) /joint_states 와 목표값 비교 (오차 < threshold)
        지금은 단순 시간 경과로 대체.
        """
        return self.elapsed() > MOTION_DURATION + 0.5


def main():
    rclpy.init()
    node = BallGraspNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
