# Import libraries
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.evaluation import evaluate_policy
from Environment import ArpodCrtbp
from stable_baselines3.common.env_checker import check_env
import matplotlib.pyplot as plt
from CallBack import CallBack

# TRAINING
# Data and initialization
m_star = 6.0458 * 1e24  # Kilograms
l_star = 3.844 * 1e8  # Meters
t_star = 375200  # Seconds

dt = 0.5
ToF = 100
batch_size = 64

rho_max = 270
rhodot_max = 20

ang_corr = np.deg2rad(20)
safety_radius = 1
safety_vel = 0.01

max_thrust = 29620
mass = 21000
state_space = 16
actions_space = 3

x0t_state = np.array(
    [
        1.02206694e00,
        -5.25240280e-07,
        -1.82100000e-01,
        -6.71943026e-07,
        -1.03353155e-01,
        2.55711651e-06,
    ]
)  # 9:2 NRO - 200m after apolune, already corrected, rt = 399069639.7170633, vt = 105.88740083894766
x0r_state = np.array(
    [
        1.70730097e-12,
        5.25240280e-07,
        -6.49763576e-12,
        6.71943026e-07,
        -5.76798331e-12,
        -2.55711651e-06,
    ]
)
x0r_mass = np.array([mass / m_star])
x0_time_rem = np.array([ToF / t_star])
x0ivp_vec = np.concatenate((x0t_state, x0r_state, x0r_mass, x0_time_rem))
x0ivp_std_vec = np.absolute(
    np.concatenate(
        (
            np.zeros(6),
            20 * np.ones(3) / l_star,
            0.1 * np.ones(3) / (l_star / t_star),
            0.005 * x0r_mass,
            np.zeros(1)
        )
    )
)

# Define environment and model
env = ArpodCrtbp(
    max_time=ToF,
    dt=dt,
    rho_max=rho_max,
    rhodot_max=rhodot_max,
    x0ivp=x0ivp_vec,
    x0ivp_std=x0ivp_std_vec,
    ang_corr=ang_corr,
    safety_radius=safety_radius,
    safety_vel=safety_vel
)
check_env(env)

# Start learning
call_back = CallBack(env)
model = PPO.load(
    "ppo_mlpBest2",
    print_system_info=True,
    custom_objects={"learning_rate": 0.0001},
    # tensorboard_log=f"tensorboard\RecurrentPPO_1",
)
print(model.policy)
model.set_env(env)
model.learn(total_timesteps=2000000, progress_bar=True, callback=call_back)

# Evaluation and saving
mean_reward, std_reward = evaluate_policy(model, env, n_eval_episodes=20, warn=False)
print(mean_reward)
model.save("ppo_mlpTLextra")


# TESTING
# Remove to demonstrate saving and loading
del model

# Loading model and reset environment
model = PPO.load("ppo_mlpTLextra")
obs = env.reset()

# Trajectory propagation
obs_vec = env.scaler_reverse_observation(obs)
rewards_vec = np.array([])
actions_vec = np.zeros(3)

while True:
    # Action sampling and propagation
    action, _states = model.predict(obs, deterministic=True)  # OSS: Episode start signals are used to reset the lstm states
    obs, rewards, done, info = env.step(action)

    # Saving
    actions_vec = np.vstack((actions_vec, env.scaler_reverse_action(action)))
    obs_vec = np.vstack((obs_vec, env.scaler_reverse_observation(obs)))
    rewards_vec = np.append(rewards_vec, rewards)

    # Stop propagation
    if done:
        break

# PLOTS
# Plotted quantities
position = obs_vec[1:-1, 6:9] * l_star
velocity = obs_vec[1:-1, 9:12] * l_star / t_star
mass = obs_vec[1:-1, 12] * m_star
thrust = actions_vec[1:-1, :] * (m_star * l_star / t_star**2)
t = np.linspace(0, ToF, int(ToF / dt))[0:len(position)]

# Approach Corridor
len_cut = np.sqrt((safety_radius**2) / np.square(np.tan(ang_corr)))
rad_kso = rho_max + len_cut
rad_entry = np.tan(ang_corr) * rad_kso
x_cone, z_cone = np.mgrid[-rad_entry:rad_entry:1000j, -rad_entry:rad_entry:1000j]
y_cone = np.sqrt((x_cone**2 + z_cone**2) / np.square(np.tan(ang_corr))) - len_cut
y_cone = np.where(y_cone > 0.8 * rho_max, np.nan, y_cone)
y_cone = np.where(y_cone < 0, np.nan, y_cone)

# Plot full trajectory ONCE
plt.close()
plt.figure()
ax = plt.axes(projection="3d")
ax.plot3D(
    position[:, 0],
    position[:, 1],
    position[:, 2],
    c="k",
    linewidth=2,
)
start = ax.scatter(
    position[0, 0],
    position[0, 1],
    position[0, 2],
    color="blue",
    marker="s",
)
stop = ax.scatter(
    position[-1, 0],
    position[-1, 1],
    position[-1, 2],
    color="red",
    marker="o",
)
goal = ax.scatter(0, 0, 0, color="green", marker="^")
plt.legend(
    (start, stop, goal),
    ("Start", "Stop", "Goal"),
    scatterpoints=1,
    loc="upper right",
)
ax.plot_surface(x_cone, y_cone, z_cone, color="k", alpha=0.1)
ax.set_xlabel("$\delta x$ [m]", labelpad=15)
plt.xticks([0])
ax.set_ylabel("$\delta y$ [m]", labelpad=10)
ax.zaxis.set_rotate_label(False)
ax.set_zlabel("$\delta z$ [m]", labelpad=10, rotation=90)
# plt.locator_params(axis="x", nbins=1)
plt.locator_params(axis="y", nbins=6)
plt.locator_params(axis="z", nbins=6)
ax.xaxis.pane.set_edgecolor("black")
ax.yaxis.pane.set_edgecolor("black")
ax.zaxis.pane.set_edgecolor("black")
ax.xaxis.pane.fill = False
ax.yaxis.pane.fill = False
ax.zaxis.pane.fill = False
ax.set_aspect("equal", "box")
ax.view_init(elev=0, azim=0)
plt.savefig("plots\TrajectoryTLextra.pdf")  # Save

# Plot relative velocity norm
plt.close()  # Initialize
plt.figure()
plt.plot(t, np.linalg.norm(velocity, axis=1), c="b", linewidth=2)
plt.grid(True)
plt.xlabel("Time [s]")
plt.ylabel("Velocity [m/s]")
plt.savefig("plots\VelocityTLextra.pdf")  # Save

# Plot relative position
plt.close()  # Initialize
plt.figure()
plt.plot(t, np.linalg.norm(position, axis=1), c="g", linewidth=2)
plt.grid(True)
plt.xlabel("Time [s]")
plt.ylabel("Position [m]")
plt.savefig("plots\PositionTLextra.pdf")  # Save

# Plot mass usage
plt.close()  # Initialize
plt.figure()
plt.plot(t, mass, c="r", linewidth=2)
plt.grid(True)
plt.xlabel("Time [s]")
plt.ylabel("Mass [kg]")
plt.savefig("plots\MassTLextra.pdf")  # Save

# Plot CoM control action
plt.close()
plt.figure()
plt.plot(
    t,
    thrust[:, 0],
    c="g",
    linewidth=2,
)
plt.plot(
    t,
    thrust[:, 1],
    c="b",
    linewidth=2,
)
plt.plot(
    t,
    thrust[:, 2],
    c="r",
    linewidth=2,
)
plt.legend(["$T_x$", "$T_y$", "$T_z$"], loc="upper right")
plt.grid(True)
plt.xlabel("Time [s]")
plt.ylabel("Thrust [N]")
plt.xlim(t[0], t[-1])
plt.savefig("plots\ThrustTLextra.pdf", bbox_inches="tight")  # Save

# Plot angular velocity
dTdt_ver = np.zeros([len(t), 3])
w_ang = np.zeros(len(t))
w_ang[0] = np.nan
dTdt_ver = np.diff(thrust / np.linalg.norm(thrust), axis=0) / dt  # Finite difference
Tb_ver = np.array([1, 0, 0])
for i in range(len(w_ang) - 1):  # OSS: T aligned with x-axis body-frame assumptions.
    wy = dTdt_ver[i, 2] / Tb_ver[0]
    wz = -dTdt_ver[i, 1] / Tb_ver[0]
    w_ang[i + 1] = np.rad2deg(np.linalg.norm(np.array([0, wy, wz])))
plt.close()  # Initialize
plt.figure()
plt.plot(t, w_ang, c="c", linewidth=2)
plt.grid(True)
plt.xlabel("Time [s]")
plt.ylabel("Angular velocity [deg/s]")
plt.savefig("plots\AngVelTLextra.pdf")  # Save

