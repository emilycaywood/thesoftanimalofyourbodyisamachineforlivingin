"""MuJoCo rollouts on CPU. Everything here is SI.

A rollout records body poses (not video) so any client can replay it in its own
scene, plus the signals metrics need. ``on_frames`` receives chunks of poses
while the simulation runs (ADR-011).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from calflab.components.library import Library
from calflab.plugins.types import ControlInfo, Controller, Observation
from calflab.schema import P
from calflab.sim.mjcf import CompiledModel


class Push(BaseModel):
    """An external force applied to a body (perturbation tool)."""

    t_s: float = 2.0
    duration_s: float = 0.15
    force_n: tuple[float, float, float] = (0.0, 20.0, 0.0)
    body: str = "trunk"


class SimSettings(BaseModel):
    duration_s: float = P(6.0, unit="s", ge=0.5, le=60, step=0.5, desc="Simulated time after settling.")
    control_hz: float = P(50.0, unit="Hz", ge=10, le=500, desc="Controller update rate.")
    record_hz: float = P(50.0, unit="Hz", ge=5, le=200, desc="Pose recording rate (playback frame rate).")
    settle_s: float = P(0.4, unit="s", ge=0.0, le=5, step=0.1, desc="Time holding the start pose before the controller runs.")
    start_pose: Literal["stand", "lying"] = P("stand", desc="Start standing or lying on the belly.")
    stop_on_fall: bool = P(True, desc="End the rollout when the robot falls.")
    seed: int = P(0, ge=0, le=2**31 - 1, ui="number", desc="Random seed (controller noise, randomization).")
    pushes: list[Push] = Field(default_factory=list, description="External pushes.", json_schema_extra={"ui": "json"})
    ambient_temp_c: float = P(22.0, ge=-10, le=50, desc="Ambient temperature for the thermal estimate.", advanced=True)


@dataclass
class Rollout:
    """Recorded simulation. Arrays are indexed [frame, ...]."""

    body_ids: list[str]
    joint_ids: list[str]
    actuator_ids: list[str]
    foot_geoms: list[str]
    t: np.ndarray  # [T] s (0 = controller start; negative while settling)
    body_pos: np.ndarray  # [T, B, 3] m
    body_quat: np.ndarray  # [T, B, 4] (w, x, y, z)
    q: np.ndarray  # [T, J] rad
    ctrl: np.ndarray  # [T, A] rad
    torque: np.ndarray  # [T, A] N*m
    dq: np.ndarray  # [T, A] rad/s
    foot_force: np.ndarray  # [T, F] N (normal)
    com: np.ndarray  # [T, 3] m
    temp: np.ndarray  # [T, A] deg C
    impacts: list[tuple[float, int, float]] = field(default_factory=list)  # (t, foot, speed m/s)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def n_frames(self) -> int:
        return int(self.t.shape[0])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "body_ids": self.body_ids,
            "joint_ids": self.joint_ids,
            "actuator_ids": self.actuator_ids,
            "foot_geoms": self.foot_geoms,
            "impacts": self.impacts,
            "meta": self.meta,
        }
        np.savez_compressed(
            path,
            t=self.t,
            body_pos=self.body_pos,
            body_quat=self.body_quat,
            q=self.q,
            ctrl=self.ctrl,
            torque=self.torque,
            dq=self.dq,
            foot_force=self.foot_force,
            com=self.com,
            temp=self.temp,
            meta=np.array(json.dumps(meta)),
        )

    @classmethod
    def load(cls, path: Path) -> Rollout:
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(str(z["meta"]))
            return cls(
                body_ids=meta["body_ids"],
                joint_ids=meta["joint_ids"],
                actuator_ids=meta["actuator_ids"],
                foot_geoms=meta["foot_geoms"],
                t=z["t"],
                body_pos=z["body_pos"],
                body_quat=z["body_quat"],
                q=z["q"],
                ctrl=z["ctrl"],
                torque=z["torque"],
                dq=z["dq"],
                foot_force=z["foot_force"],
                com=z["com"],
                temp=z["temp"],
                impacts=[tuple(i) for i in meta["impacts"]],  # type: ignore[misc]
                meta=meta["meta"],
            )


def _lying_pose(cm: CompiledModel) -> tuple[dict[str, float], float]:
    """Joint angles (rad) and trunk height (m) for lying on the belly, legs folded."""
    pose = dict(cm.rest)
    for jid, (lo, hi) in cm.limits.items():
        if jid.endswith(".knee"):
            pose[jid] = lo * 0.92 if cm.rest[jid] < 0 else hi * 0.92
        elif jid.endswith(".hip_flex"):
            pose[jid] = (hi if cm.rest[jid] > 0 else lo) * 0.9
    return pose, 0.12


def run_rollout(
    cm: CompiledModel,
    controller: Controller,
    settings: SimSettings,
    lib: Library | None = None,
    on_frames: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    chunk_frames: int = 15,
    record: bool = True,
) -> Rollout:
    """Simulate ``cm`` under ``controller``. Deterministic for fixed inputs and seed."""
    import mujoco

    model = mujoco.MjModel.from_xml_string(cm.xml)
    data = mujoco.MjData(model)

    nA = len(cm.actuator_ids)
    jadr = np.array([model.jnt_qposadr[model.joint(j).id] for j in cm.joint_ids], dtype=int)
    act_j = [model.joint(j).id for j in cm.actuator_joint]
    a_qadr = np.array([model.jnt_qposadr[j] for j in act_j], dtype=int)
    a_dadr = np.array([model.jnt_dofadr[j] for j in act_j], dtype=int)
    body_idx = np.array([model.body(b).id for b in cm.body_ids], dtype=int)
    trunk = int(body_idx[0])
    floor = model.geom("floor").id
    foot_idx = {model.geom(g).id: i for i, g in enumerate(cm.foot_geoms)}
    foot_gid = np.array(list(foot_idx.keys()), dtype=int)
    nF = len(foot_idx)

    rest = np.array([cm.rest[j] for j in cm.actuator_joint])
    lo = np.array([cm.limits[j][0] for j in cm.actuator_joint])
    hi = np.array([cm.limits[j][1] for j in cm.actuator_joint])

    # ---- initial state
    mujoco.mj_resetDataKeyframe(model, data, 0)
    start = rest.copy()
    if settings.start_pose == "lying":
        pose, height = _lying_pose(cm)
        for jid, adr in zip(cm.joint_ids, jadr, strict=True):
            data.qpos[adr] = pose[jid]
        data.qpos[2] = height
        start = np.array([pose[j] for j in cm.actuator_joint])
    data.ctrl[:] = start
    mujoco.mj_forward(model, data)

    dt = model.opt.timestep
    n_sub = max(1, int(round(1.0 / (settings.control_hz * dt))))
    control_dt = n_sub * dt
    rec_every = max(1, int(round(settings.control_hz / settings.record_hz)))
    n_settle = int(round(settings.settle_s / control_dt))
    n_steps = n_settle + int(round(settings.duration_s / control_dt))

    info = ControlInfo(
        actuator_ids=list(cm.actuator_ids),
        joint_ids=list(cm.actuator_joint),
        rest=rest,
        lo=lo,
        hi=hi,
        control_dt=control_dt,
    )
    controller.reset(info, settings.seed)

    # thermal model constants per actuator
    if lib is not None:
        comps = [lib.actuator(c) for c in cm.actuator_component]
        stall = np.array(cm.actuator_stall)
        kt = stall / np.array([max(c.stall_current_a, 1e-9) for c in comps])
        r_el = np.array([c.winding_resistance_ohm for c in comps])
        r_th = np.array([c.r_thermal_k_per_w for c in comps])
        c_th = np.array([c.c_thermal_j_per_k for c in comps])
        idle = np.array([c.idle_current_a for c in comps])
    else:
        kt = np.ones(nA)
        r_el = np.zeros(nA)
        r_th = np.ones(nA)
        c_th = np.ones(nA)
        idle = np.zeros(nA)
    temp = np.full(nA, settings.ambient_temp_c)

    pushes = [(p, model.body(p.body).id) for p in settings.pushes]

    rec: dict[str, list[Any]] = {
        k: [] for k in ("t", "pos", "quat", "q", "ctrl", "torque", "dq", "ff", "com", "temp")
    }
    impacts: list[tuple[float, int, float]] = []
    prev_contact = np.zeros(nF, dtype=bool)
    prev_foot_z = data.geom_xpos[foot_gid, 2].copy() if nF else np.zeros(0)
    foot_vz = np.zeros(nF)
    energy = 0.0
    fell = False
    fall_time: float | None = None
    force_buf = np.zeros(6)
    pending_from = 0
    target = start.copy()
    stood_since: float | None = None
    time_to_stand: float | None = None
    stand_h = cm.root_height

    def contacts() -> np.ndarray:
        ff = np.zeros(nF)
        for i in range(data.ncon):
            c = data.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            other = g2 if g1 == floor else (g1 if g2 == floor else -1)
            fi = foot_idx.get(other)
            if fi is not None:
                mujoco.mj_contactForce(model, data, i, force_buf)
                ff[fi] += force_buf[0]
        return ff

    for step in range(n_steps + 1):
        t = (step - n_settle) * control_dt
        ff = contacts()
        contact = ff > 1e-6
        q_act = data.qpos[a_qadr].copy()
        dq_act = data.qvel[a_dadr].copy()
        torque = data.actuator_force[:nA].copy() if nA else np.zeros(0)

        # ---- per-control-step accumulators
        if nF:
            z = data.geom_xpos[foot_gid, 2]
            foot_vz = (z - prev_foot_z) / control_dt
            prev_foot_z = z.copy()
            if step > 0 and t >= 0:
                for fi in np.nonzero(contact & ~prev_contact)[0]:
                    impacts.append((float(t), int(fi), float(abs(foot_vz[fi]))))
            prev_contact = contact
        if t >= 0:
            energy += float(np.sum(np.abs(torque * dq_act))) * control_dt
        current = np.abs(torque) / kt + idle
        temp = temp + (current**2 * r_el - (temp - settings.ambient_temp_c) / r_th) / c_th * control_dt

        up_z = float(data.xmat[trunk].reshape(3, 3)[2, 2])
        height = float(data.xpos[trunk][2])
        if settings.start_pose == "lying":
            standing = height > 0.85 * stand_h and up_z > 0.9
            if standing and time_to_stand is None:
                stood_since = t if stood_since is None else stood_since
                if t - stood_since >= 0.5:
                    time_to_stand = float(stood_since + settings.settle_s)
            elif not standing:
                stood_since = None
        elif t >= 0 and not fell and (height < 0.45 * stand_h or up_z < 0.4):
            fell = True
            fall_time = float(t)

        if record and step % rec_every == 0:
            rec["t"].append(t)
            rec["pos"].append(data.xpos[body_idx].astype(np.float32))
            rec["quat"].append(data.xquat[body_idx].astype(np.float32))
            rec["q"].append(data.qpos[jadr].astype(np.float32))
            rec["ctrl"].append(target.astype(np.float32))
            rec["torque"].append(torque.astype(np.float32))
            rec["dq"].append(dq_act.astype(np.float32))
            rec["ff"].append(ff.astype(np.float32))
            rec["com"].append(data.subtree_com[trunk].astype(np.float32))
            rec["temp"].append(temp.astype(np.float32))
            n = len(rec["t"])
            if on_frames and (n - pending_from >= chunk_frames):
                on_frames(_chunk(rec, pending_from, n))
                pending_from = n

        if step == n_steps or (fell and settings.stop_on_fall and t > (fall_time or 0) + 0.3):
            break
        if cancelled and step % 25 == 0 and cancelled():
            break

        # ---- control
        if t < 0:
            target = start
        else:
            obs = Observation(
                t=t,
                q=q_act,
                dq=dq_act,
                trunk_quat=data.xquat[trunk].copy(),
                trunk_gyro=data.sensordata[0:3].copy(),
                foot_contact=contact.astype(float),
            )
            target = np.clip(np.asarray(controller.act(obs), dtype=float), lo, hi)
            if settings.start_pose == "lying":  # ease from the folded pose into the controller
                w = min(1.0, t / 1.5)
                target = (1 - w) * start + w * target
        data.ctrl[:nA] = target

        data.xfrc_applied[:] = 0.0
        for p, bid in pushes:
            if p.t_s <= t < p.t_s + p.duration_s:
                data.xfrc_applied[bid, :3] = p.force_n

        for _ in range(n_sub):
            mujoco.mj_step(model, data)

    n = len(rec["t"])
    if on_frames and n > pending_from:
        on_frames(_chunk(rec, pending_from, n))

    def arr(key: str, shape: tuple[int, ...]) -> np.ndarray:
        return np.stack(rec[key]) if rec[key] else np.zeros((0, *shape), dtype=np.float32)

    nB, nJ = len(cm.body_ids), len(cm.joint_ids)
    return Rollout(
        body_ids=list(cm.body_ids),
        joint_ids=list(cm.joint_ids),
        actuator_ids=list(cm.actuator_ids),
        foot_geoms=list(cm.foot_geoms),
        t=np.array(rec["t"], dtype=np.float64),
        body_pos=arr("pos", (nB, 3)),
        body_quat=arr("quat", (nB, 4)),
        q=arr("q", (nJ,)),
        ctrl=arr("ctrl", (nA,)),
        torque=arr("torque", (nA,)),
        dq=arr("dq", (nA,)),
        foot_force=arr("ff", (nF,)),
        com=arr("com", (3,)),
        temp=arr("temp", (nA,)),
        impacts=impacts,
        meta={
            "energy_j": energy,
            "fell": fell,
            "fall_time": fall_time,
            "time_to_stand": time_to_stand,
            "duration_s": settings.duration_s,
            "settle_s": settings.settle_s,
            "start_pose": settings.start_pose,
            "seed": settings.seed,
            "control_dt": control_dt,
            "record_dt": control_dt * rec_every,
            "total_mass_kg": cm.total_mass_kg,
            "root_height": cm.root_height,
            "actuator_joint": list(cm.actuator_joint),
            "torque_limit": list(cm.actuator_torque_limit),
            "limits": {k: list(v) for k, v in cm.limits.items()},
            "final_temp": [float(x) for x in temp],
            "scales": cm.scales,
        },
    )


def _chunk(rec: dict[str, list[Any]], a: int, b: int) -> dict[str, Any]:
    return {
        "start": a,
        "t": np.array(rec["t"][a:b]),
        "pos": np.stack(rec["pos"][a:b]),
        "quat": np.stack(rec["quat"][a:b]),
    }
