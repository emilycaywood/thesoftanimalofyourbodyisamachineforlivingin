// World-space overlays: grid, centre of mass, support polygon, contact forces,
// harness routes, sensors. Values come from the server (design pose) or from the
// recorded rollout (playback); nothing is computed here beyond drawing.
import { Grid, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { LayerState, Scene } from "@/api/types";
import { currentFrameIndex, usePlayback } from "@/store/playback";
import { useView } from "@/store/view";

const MAX_POLY = 16;

export function Overlays({ scene, layers }: { scene: Scene; layers: Record<string, LayerState> }) {
  const overlays = useView((s) => s.overlays);
  const theme = useView((s) => s.theme);
  const playing = usePlayback((s) => s.source !== "none");
  const com = useRef<THREE.Group>(null);
  const comLine = useRef<THREE.Line>(null);
  const arrows = useRef<THREE.ArrowHelper[]>([]);

  const poly = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(MAX_POLY * 3), 3));
    const line = new THREE.LineLoop(geom, new THREE.LineBasicMaterial({ color: "#57b97a", depthTest: false }));
    line.renderOrder = 9;
    line.frustumCulled = false;
    return line;
  }, []);
  const comDrop = useMemo(() => {
    const geom = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
    const line = new THREE.Line(geom, new THREE.LineDashedMaterial({ color: "#e0a83d", dashSize: 12, gapSize: 8, depthTest: false }));
    line.frustumCulled = false;
    return line;
  }, []);
  const contactArrows = useMemo(
    () =>
      scene.feet.map(() => {
        const a = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), 1, "#4fa3d4", 14, 9);
        a.visible = false;
        return a;
      }),
    [scene.feet],
  );
  arrows.current = contactArrows;

  useFrame(() => {
    const i = currentFrameIndex();
    const pb = usePlayback.getState();
    // centre of mass
    const c = i >= 0 && pb.com[i] ? pb.com[i] : scene.com;
    if (com.current) com.current.position.set(c[0], c[1], c[2]);
    const pos = comDrop.geometry.getAttribute("position") as THREE.BufferAttribute;
    pos.setXYZ(0, c[0], c[1], c[2]);
    pos.setXYZ(1, c[0], c[1], 0.5);
    pos.needsUpdate = true;
    comDrop.computeLineDistances();
    // support polygon
    const pts = i >= 0 && pb.support.length ? (pb.support[i] ?? []) : i >= 0 ? [] : scene.support_polygon;
    const attr = poly.geometry.getAttribute("position") as THREE.BufferAttribute;
    const n = Math.min(pts.length, MAX_POLY);
    for (let k = 0; k < n; k++) attr.setXYZ(k, pts[k][0], pts[k][1], 1);
    attr.needsUpdate = true;
    poly.geometry.setDrawRange(0, n);
    // contact forces (playback only)
    for (let f = 0; f < arrows.current.length; f++) {
      const arrow = arrows.current[f];
      const force = i >= 0 ? (pb.footForce[i]?.[f] ?? 0) : 0;
      const p = i >= 0 ? pb.footPos[i]?.[f] : undefined;
      if (force > 0.5 && p) {
        arrow.visible = true;
        arrow.position.set(p[0], p[1], p[2]);
        arrow.setLength(Math.min(260, 20 + force * 2.2), 14, 9);
      } else arrow.visible = false;
    }
  });

  const harnessVisible = overlays.harness && !playing && layers.Harness?.visible !== false;
  const sensorsVisible = overlays.sensors && !playing && layers.Sensors?.visible !== false;
  return (
    <>
      {overlays.grid && (
        <Grid
          rotation={[Math.PI / 2, 0, 0]}
          position={[0, 0, -0.5]}
          args={[20000, 20000]}
          cellSize={50}
          sectionSize={250}
          cellThickness={0.6}
          sectionThickness={1}
          cellColor={theme === "dark" ? "#39424e" : "#c3c9d1"}
          sectionColor={theme === "dark" ? "#4d5866" : "#a9b1bc"}
          fadeDistance={9000}
          fadeStrength={1.5}
          infiniteGrid
        />
      )}
      {overlays.com && (
        <>
          <group ref={com} renderOrder={11}>
            <mesh>
              <sphereGeometry args={[9, 16, 12]} />
              <meshBasicMaterial color="#e0a83d" depthTest={false} />
            </mesh>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[13, 1.2, 8, 32]} />
              <meshBasicMaterial color="#1b1b1b" depthTest={false} />
            </mesh>
          </group>
          <primitive object={comDrop} ref={comLine} />
        </>
      )}
      {overlays.support && <primitive object={poly} />}
      {overlays.contacts && contactArrows.map((a, i) => <primitive key={i} object={a} />)}
      {harnessVisible &&
        scene.harness.map(
          (h) =>
            h.points.length > 1 && (
              <Line key={h.id} points={h.points} color={layers.Harness?.color ?? "#c4504e"} lineWidth={2} depthTest={false} />
            ),
        )}
      {sensorsVisible &&
        scene.sensors.map((s) => (
          <mesh key={s.id} position={s.pos} renderOrder={8}>
            <octahedronGeometry args={[7]} />
            <meshBasicMaterial color={layers.Sensors?.color ?? "#3f9fd4"} depthTest={false} />
          </mesh>
        ))}
    </>
  );
}
