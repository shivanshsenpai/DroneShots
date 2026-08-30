"""
Kalman Filter for 3D Target State Estimation and Occlusion Prediction.
Filters noisy detections and predicts target position during brief occlusions.
"""
import numpy as np


class KalmanTargetFilter:
    def __init__(self):
        # State vector: [x, y, area, vx, vy, varea]
        self.state = np.zeros(6, dtype=np.float32)
        
        # State transition matrix (dt = 1/30s)
        self.dt = 1.0 / 30.0
        self.F = np.array([
            [1, 0, 0, self.dt, 0, 0],
            [0, 1, 0, 0, self.dt, 0],
            [0, 0, 1, 0, 0, self.dt],
            [0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1]
        ], dtype=np.float32)

        # Measurement matrix: we measure [x, y, area]
        self.H = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0]
        ], dtype=np.float32)

        # Covariance matrices
        self.P = np.eye(6, dtype=np.float32) * 10.0
        self.Q = np.eye(6, dtype=np.float32) * 0.05   # Process noise
        self.R = np.eye(3, dtype=np.float32) * 0.10   # Measurement noise

        self.initialized = False
        self.missed_frames = 0

    def reset(self):
        self.state = np.zeros(6, dtype=np.float32)
        self.P = np.eye(6, dtype=np.float32) * 10.0
        self.initialized = False
        self.missed_frames = 0

    def predict(self) -> np.ndarray:
        """Predicts the next state."""
        self.state = np.dot(self.F, self.state)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return self.state[:3]

    def update(self, x: float, y: float, area: float) -> np.ndarray:
        """Updates the filter with a new measurement."""
        measurement = np.array([x, y, area], dtype=np.float32)

        if not self.initialized:
            self.state[:3] = measurement
            self.state[3:] = 0.0
            self.initialized = True
            self.missed_frames = 0
            return self.state[:3]

        # Prediction step
        self.predict()

        # Update step
        y_residual = measurement - np.dot(self.H, self.state)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))

        self.state = self.state + np.dot(K, y_residual)
        self.P = np.dot((np.eye(6, dtype=np.float32) - np.dot(K, self.H)), self.P)
        self.missed_frames = 0

        return self.state[:3]

    def step_missed(self) -> np.ndarray:
        """Advances prediction when target is temporarily lost."""
        self.missed_frames += 1
        return self.predict()
