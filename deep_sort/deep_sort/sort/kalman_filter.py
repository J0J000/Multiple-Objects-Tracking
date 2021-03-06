# vim: expandtab:ts=4:sw=4
import numpy as np
import scipy.linalg

chi2inv95 = {
    1: 3.8415,
    2: 5.9915,
    3: 7.8147,
    4: 9.4877,
    5: 11.070,
    6: 12.592,
    7: 14.067,
    8: 15.507,
    9: 16.919}

#卡尔曼滤波，用于估计track状态，包括：
#均值：8维向量（ x, y, a, h, vx, vy, va, vh）表示
#     （x,y）-框的中心坐标 a-宽高比 h-高度 vx, vy, va, vh-速度，初始化为0
#协方差：表示目标位置信息的不确定性，用8x8对角矩阵表示，矩阵值越大表示不确定程度越高
class KalmanFilter(object):

    def __init__(self):
        ndim, dt = 4, 1.

        self._motion_mat = np.eye(2 * ndim, 2 * ndim)
        for i in range(ndim):
            self._motion_mat[i, ndim + i] = dt
        self._update_mat = np.eye(ndim, 2 * ndim)

        self._std_weight_position = 1. / 20
        self._std_weight_velocity = 1. / 160

    def initiate(self, measurement):
        mean_pos = measurement
        mean_vel = np.zeros_like(mean_pos)
        mean = np.r_[mean_pos, mean_vel]

        std = [
            2 * self._std_weight_position * measurement[3],
            2 * self._std_weight_position * measurement[3],
            1e-2,
            2 * self._std_weight_position * measurement[3],
            10 * self._std_weight_velocity * measurement[3],
            10 * self._std_weight_velocity * measurement[3],
            1e-5,
            10 * self._std_weight_velocity * measurement[3]]
        covariance = np.diag(np.square(std))
        return mean, covariance

    def predict(self, mean, covariance):
        #相当于得到t时刻的估计值

        # Q - 预测过程中的噪音协方差
        std_pos = [
            self._std_weight_position * mean[3],
            self._std_weight_position * mean[3],
            1e-2,
            self._std_weight_position * mean[3]]
        std_vel = [
            self._std_weight_velocity * mean[3],
            self._std_weight_velocity * mean[3],
            1e-5,
            self._std_weight_velocity * mean[3]]

        #初始化噪音矩阵Q
        motion_cov = np.diag(np.square(np.r_[std_pos, std_vel])) #np.r_按列连接两个矩阵

        #x'=Fx （F是状态转移矩阵）
        mean = np.dot(self._motion_mat, mean)

        #P'=FPF^T+Q （P是当前帧的协方差；Q是卡尔曼滤波器的运动估计误差，代表不确定性）
        covariance = np.linalg.multi_dot((
            self._motion_mat, covariance, self._motion_mat.T)) + motion_cov

        return mean, covariance

    def project(self, mean, covariance):

        #R - 测量过程中的噪音协方差
        std = [
            self._std_weight_position * mean[3],
            self._std_weight_position * mean[3],
            1e-1,
            self._std_weight_position * mean[3]]

        #初始化噪音矩阵R
        innovation_cov = np.diag(np.square(std))

        #将均值向量映射到检测空间，即Hx'
        mean = np.dot(self._update_mat, mean)

        #将协方差矩阵映射到检测空间，即HP'H^T
        covariance = np.linalg.multi_dot((
            self._update_mat, covariance, self._update_mat.T))
        return mean, covariance + innovation_cov

    def update(self, mean, covariance, measurement):
    #通过估计值和观测值得到最新结果

        # 将均值和协方差映射到检测空间，得到Hx'和S
        projected_mean, projected_cov = self.project(mean, covariance)

        # 矩阵分解
        chol_factor, lower = scipy.linalg.cho_factor(
            projected_cov, lower=True, check_finite=False)
        # 计算卡尔曼增益K
        kalman_gain = scipy.linalg.cho_solve(
            (chol_factor, lower), np.dot(covariance, self._update_mat.T).T,
            check_finite=False).T
        # z-Hx'
        innovation = measurement - projected_mean

        # x=x'+Ky
        new_mean = mean + np.dot(innovation, kalman_gain.T)
        # P=(I-KH)P'
        new_covariance = covariance - np.linalg.multi_dot((
            kalman_gain, projected_cov, kalman_gain.T))
        return new_mean, new_covariance

    def gating_distance(self, mean, covariance, measurements,
                        only_position=False):
        mean, covariance = self.project(mean, covariance)
        if only_position:
            mean, covariance = mean[:2], covariance[:2, :2]
            measurements = measurements[:, :2]

        cholesky_factor = np.linalg.cholesky(covariance)
        d = measurements - mean
        z = scipy.linalg.solve_triangular(
            cholesky_factor, d.T, lower=True, check_finite=False,
            overwrite_b=True)
        squared_maha = np.sum(z * z, axis=0)
        return squared_maha
