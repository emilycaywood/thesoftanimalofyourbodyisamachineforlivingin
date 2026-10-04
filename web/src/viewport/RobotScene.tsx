// The robot in the three.js scene. Bodies are flat groups keyed by stable ID
// and posed in world coordinates (mm, Z-up); simulation playback drives the
// same groups, so every display mode and overlay works during playback.
import { Edges, useGLTF } from "@react-three/drei";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { api } from "@/api/client";
import type { BodyInfo, GeomInfo, JointInfo, LayerState, Scene } from "@/api/types";
import { currentFrameIndex, usePlayback } from "@/store/playback";
import { useView, type DisplayMode } from "@/store/view";

export type BodyGroups = Map<string, THREE.Group>;

const HALF_PI = Math.PI / 2;
const AXIS_COLORS: Record<string, string> = { x: "#e05a52", y: "#57b97a", z: "#4f8fe0" };

function massColor(share: number): string {
  // blue (light) -> red (heavy)
  const h = (1 - Math.min(1, share * 3)) * 0.62;
  return new THREE.Color().setHSL(h, 0.75, 0.5).getStyle();
}

function GeomShape({ geom }: { geom: GeomInfo }) {
  const [a, b, c] = geom.size;
  switch (geom.shape) {
    case "box":
      return <boxGeometry args={[a, b, c]} />;
    case "sphere":
      return <sphereGeometry args={[a, 24, 16]} />;
    case "ellipsoid":
      return <sphereGeometry args={[1, 32, 20]} />;
    case "capsule":
      return <capsuleGeometry args={[a, b, 8, 20]} />;
    case "cylinder":
      return <cylinderGeometry args={[a, a, b, 24]} />;
    default:
      return <sphereGeometry args={[5, 8, 8]} />;
  }
}

function MeshAsset({ path, material }: { path: string; material: THREE.Material }) {
  const gltf = useGLTF(api.fileUrl(path));
  const object = useMemo(() => {
    const clone = gltf.scene.clone(true);
    clone.traverse((o) => {
      if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).material = material;
    });
    return clone;
  }, [gltf, material]);
  return <primitive object={object} />;
}

function makeMaterial(mode: DisplayMode, color: string, layer: string, selected: boolean): THREE.Material {
  const skin = layer === "Skin";
  const c = new THREE.Color(color);
  const emissive = selected ? new THREE.Color("#e0823d") : new THREE.Color(0);
  const emissiveIntensity = selected ? 0.45 : 0;
  switch (mode) {
    case "wireframe":
      return new THREE.MeshBasicMaterial({ color: selected ? "#e0823d" : c, wireframe: true });
    case "ghosted":
      return new THREE.MeshStandardMaterial({
        color: c, transparent: true, opacity: skin ? 0.12 : 0.35, depthWrite: false, emissive, emissiveIntensity, roughness: 0.8,
      });
    case "xray":
      return new THREE.MeshBasicMaterial({
        color: selected ? "#e0823d" : c, transparent: true, opacity: skin ? 0.08 : 0.25, depthTest: false, depthWrite: false,
      });
    case "rendered":
      return skin
        ? new THREE.MeshPhysicalMaterial({ color: c, roughness: 0.62, sheen: 0.6, sheenRoughness: 0.5, clearcoat: 0.05, emissive, emissiveIntensity })
        : new THREE.MeshPhysicalMaterial({ color: c, roughness: 0.45, metalness: layer === "Actuators" ? 0.5 : 0.05, emissive, emissiveIntensity });
    default:
      return new THREE.MeshStandardMaterial({
        color: c, roughness: 0.75, metalness: 0.05, transparent: skin, opacity: skin ? 0.3 : 1, depthWrite: !skin, emissive, emissiveIntensity,
      });
  }
}

function GeomMesh({
  geom,
  bodyId,
  color,
  mode,
  selected,
  pickable,
  onPick,
}: {
  geom: GeomInfo;
  bodyId: string;
  color: string;
  mode: DisplayMode;
  selected: boolean;
  pickable: boolean;
  onPick: (e: ThreeEvent<MouseEvent>, bodyId: string, geomId: string) => void;
}) {
  const material = useMemo(() => makeMaterial(mode, color, geom.layer, selected), [mode, color, geom.layer, selected]);
  useEffect(() => () => material.dispose(), [material]);
  const [qw, qx, qy, qz] = geom.quat;
  const yAxis = geom.shape === "capsule" || geom.shape === "cylinder"; // three builds these along Y; ours are along Z
  const scale: [number, number, number] = geom.shape === "ellipsoid" ? geom.size : [1, 1, 1];
  const rendered = mode === "rendered";
  return (
    <group position={geom.pos} quaternion={[qx, qy, qz, qw]}>
      {geom.shape === "mesh" && geom.mesh ? (
        <group
          userData={{ bodyId, geomId: geom.id }}
          onClick={pickable ? (e) => onPick(e, bodyId, geom.id) : undefined}
        >
          <Suspense fallback={null}>
            <MeshAsset path={geom.mesh} material={material} />
          </Suspense>
        </group>
      ) : (
        <mesh
          material={material}
          rotation={yAxis ? [HALF_PI, 0, 0] : [0, 0, 0]}
          scale={scale}
          castShadow={rendered && geom.layer !== "Skin"}
          receiveShadow={rendered}
          renderOrder={geom.layer === "Skin" ? 2 : 1}
          userData={{ bodyId, geomId: geom.id }}
          onClick={pickable ? (e) => onPick(e, bodyId, geom.id) : undefined}
        >
          <GeomShape geom={geom} />
          {selected && mode !== "wireframe" && <Edges threshold={25} color="#ffb070" />}
          {mode === "ghosted" && !selected && <Edges threshold={25} color={color} />}
        </mesh>
      )}
    </group>
  );
}

/** Joint axis and limit arc, drawn in the parent body's frame so it stays put while the child moves. */
function JointGizmo({ joint, child }: { joint: JointInfo; child: BodyInfo }) {
  const [qw, qx, qy, qz] = child.local_quat;
  const { axisGeom, arcGeom, restGeom, color } = useMemo(() => {
    const axis = new THREE.Vector3(...joint.axis).normalize();
    const dominant = Math.abs(axis.x) > 0.9 ? "x" : Math.abs(axis.y) > 0.9 ? "y" : "z";
    const len = 45;
    const axisGeom = new THREE.BufferGeometry().setFromPoints([axis.clone().multiplyScalar(-len), axis.clone().multiplyScalar(len)]);
    // reference direction for angle zero: the child's "down" (or forward) projected off the axis
    let ref = new THREE.Vector3(0, 0, -1);
    if (Math.abs(ref.dot(axis)) > 0.9) ref = new THREE.Vector3(1, 0, 0);
    ref.sub(axis.clone().multiplyScalar(ref.dot(axis))).normalize();
    const radius = 32;
    const [lo, hi] = joint.range_deg.map(THREE.MathUtils.degToRad);
    const pts: THREE.Vector3[] = [new THREE.Vector3()];
    const steps = 24;
    for (let i = 0; i <= steps; i++) {
      const a = lo + ((hi - lo) * i) / steps;
      pts.push(ref.clone().applyAxisAngle(axis, a).multiplyScalar(radius));
    }
    pts.push(new THREE.Vector3());
    const arcGeom = new THREE.BufferGeometry().setFromPoints(pts);
    const rest = ref.clone().applyAxisAngle(axis, THREE.MathUtils.degToRad(joint.rest_deg)).multiplyScalar(radius * 1.25);
    const restGeom = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), rest]);
    return { axisGeom, arcGeom, restGeom, color: AXIS_COLORS[dominant] };
  }, [joint]);
  useEffect(
    () => () => {
      axisGeom.dispose();
      arcGeom.dispose();
      restGeom.dispose();
    },
    [axisGeom, arcGeom, restGeom],
  );
  const lines = useMemo(() => {
    const mat = new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.9 });
    const restMat = new THREE.LineBasicMaterial({ color: "#ffffff", depthTest: false });
    return [new THREE.Line(axisGeom, mat), new THREE.Line(arcGeom, mat), new THREE.Line(restGeom, restMat)];
  }, [axisGeom, arcGeom, restGeom, color]);
  return (
    <group position={child.local_pos} quaternion={[qx, qy, qz, qw]} renderOrder={10}>
      {lines.map((line, i) => (
        <primitive key={i} object={line} />
      ))}
    </group>
  );
}

export function RobotScene({
  scene,
  layers,
  groups,
}: {
  scene: Scene;
  layers: Record<string, LayerState>;
  groups: React.MutableRefObject<BodyGroups>;
}) {
  const mode = useView((s) => s.displayMode);
  const selection = useView((s) => s.selection);
  const hidden = useView((s) => s.hidden);
  const isolated = useView((s) => s.isolated);
  const overlays = useView((s) => s.overlays);
  const filter = useView((s) => s.selectionFilter);
  const measure = useView((s) => s.measure);
  const applied = useRef(-2);

  const sel = useMemo(() => new Set(selection), [selection]);
  const hid = useMemo(() => new Set(hidden), [hidden]);
  const iso = useMemo(() => (isolated ? new Set(isolated) : null), [isolated]);
  const bodyById = useMemo(() => new Map(scene.bodies.map((b) => [b.id, b])), [scene]);
  const jointsByParent = useMemo(() => {
    const m = new Map<string, JointInfo[]>();
    for (const j of scene.joints) {
      if (!j.parent_body) continue;
      m.set(j.parent_body, [...(m.get(j.parent_body) ?? []), j]);
    }
    return m;
  }, [scene]);

  const onPick = (e: ThreeEvent<MouseEvent>, bodyId: string, geomId: string) => {
    if (measure) return; // the measure tool takes the click
    e.stopPropagation();
    const id = filter === "body" ? bodyId : geomId;
    useView.getState().select([id], e.shiftKey || e.ctrlKey || e.metaKey);
  };

  // Drive body poses from playback (or restore the design pose).
  useFrame(() => {
    const i = currentFrameIndex();
    if (i === applied.current && i < 0) return;
    const pb = usePlayback.getState();
    if (i < 0) {
      for (const b of scene.bodies) {
        const g = groups.current.get(b.id);
        if (!g) continue;
        g.position.set(b.pos[0], b.pos[1], b.pos[2]);
        g.quaternion.set(b.quat[1], b.quat[2], b.quat[3], b.quat[0]);
      }
    } else {
      const pos = pb.pos[i];
      const quat = pb.quat[i];
      for (let k = 0; k < pb.bodyIds.length; k++) {
        const g = groups.current.get(pb.bodyIds[k]);
        if (!g) continue;
        g.position.set(pos[3 * k], pos[3 * k + 1], pos[3 * k + 2]);
        g.quaternion.set(quat[4 * k + 1], quat[4 * k + 2], quat[4 * k + 3], quat[4 * k]);
      }
    }
    applied.current = i;
  });
  // a new scene must be re-posed even when idle
  useEffect(() => {
    applied.current = -2;
  }, [scene]);

  const total = scene.mass.total_g || 1;
  return (
    <group name="robot">
      {scene.bodies.map((body) => {
        const [qw, qx, qy, qz] = body.quat;
        const bodyHidden = hid.has(body.id) || (iso !== null && !iso.has(body.id) && !body.geoms.some((g) => iso.has(g.id)));
        return (
          <group
            key={body.id}
            name={body.id}
            ref={(g) => {
              if (g) groups.current.set(body.id, g);
              else groups.current.delete(body.id);
            }}
            position={body.pos}
            quaternion={[qx, qy, qz, qw]}
            visible={!bodyHidden}
          >
            {body.geoms.map((geom) => {
              const layer = layers[geom.layer];
              if (layer && !layer.visible) return null;
              if (hid.has(geom.id)) return null;
              if (overlays.collision && geom.role === "visual") return null;
              const color = overlays.massColors
                ? massColor((scene.mass.by_body_g[body.id] ?? 0) / total)
                : (geom.color ?? layer?.color ?? "#b9c0c9");
              return (
                <GeomMesh
                  key={geom.id}
                  geom={geom}
                  bodyId={body.id}
                  color={color}
                  mode={mode}
                  selected={sel.has(body.id) || sel.has(geom.id)}
                  pickable={!layer?.locked && !bodyHidden}
                  onPick={onPick}
                />
              );
            })}
            {overlays.jointAxes &&
              (jointsByParent.get(body.id) ?? []).map((j) => {
                const child = bodyById.get(j.body);
                return child ? <JointGizmo key={j.id} joint={j} child={child} /> : null;
              })}
          </group>
        );
      })}
    </group>
  );
}
