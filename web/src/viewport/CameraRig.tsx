// Cameras and navigation. Presets follow the conventions of the tool they are
// named after: Rhino (RMB orbit, Shift+RMB pan, wheel zoom), Blender (MMB orbit,
// Shift+MMB pan), Fusion (MMB pan, Shift+MMB orbit).
import { OrbitControls, OrthographicCamera, PerspectiveCamera } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { useView, type NavPreset, type ViewName } from "@/store/view";
import type { BodyGroups } from "./RobotScene";

const NONE = -1 as unknown as THREE.MOUSE;

function buttons(nav: NavPreset, ortho: boolean) {
  if (nav === "blender") return { LEFT: NONE, MIDDLE: ortho ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE, RIGHT: NONE };
  if (nav === "fusion") return { LEFT: NONE, MIDDLE: THREE.MOUSE.PAN, RIGHT: NONE };
  return { LEFT: NONE, MIDDLE: THREE.MOUSE.PAN, RIGHT: ortho ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE };
}

const VIEW_POSE: Record<ViewName, { position: [number, number, number]; up: [number, number, number] }> = {
  perspective: { position: [1350, -1500, 950], up: [0, 0, 1] },
  top: { position: [0, 0, 6000], up: [0, 1, 0] },
  front: { position: [0, -6000, 300], up: [0, 0, 1] },
  right: { position: [6000, 0, 300], up: [0, 0, 1] },
};
const TARGET: [number, number, number] = [0, 0, 300];

export function CameraRig({ view, groups, active }: { view: ViewName; groups: React.MutableRefObject<BodyGroups>; active: boolean }) {
  const nav = useView((s) => s.nav);
  const request = useView((s) => s.cameraRequest);
  const controls = useRef<OrbitControlsImpl>(null);
  const { camera, size } = useThree();
  const ortho = view !== "perspective";
  const lastRequest = useRef(request.id);

  const fit = (ids: string[] | null) => {
    const box = new THREE.Box3();
    for (const [id, g] of groups.current) {
      if (ids && !ids.includes(id)) continue;
      if (g.visible) box.expandByObject(g);
    }
    if (box.isEmpty()) return;
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const c = controls.current;
    if (!c) return;
    const dir = camera.position.clone().sub(c.target).normalize();
    c.target.copy(sphere.center);
    if ((camera as THREE.OrthographicCamera).isOrthographicCamera) {
      const cam = camera as THREE.OrthographicCamera;
      cam.position.copy(sphere.center).add(dir.multiplyScalar(6000));
      cam.zoom = Math.min(size.width, size.height) / (2.3 * sphere.radius);
      cam.updateProjectionMatrix();
    } else {
      const cam = camera as THREE.PerspectiveCamera;
      const dist = (sphere.radius * 1.25) / Math.sin(THREE.MathUtils.degToRad(cam.fov / 2));
      cam.position.copy(sphere.center).add(dir.multiplyScalar(dist));
    }
    c.update();
  };

  // set the pose when the view changes
  useEffect(() => {
    const pose = VIEW_POSE[view];
    camera.up.set(...pose.up);
    camera.position.set(...pose.position);
    const c = controls.current;
    if (c) {
      c.target.set(...TARGET);
      c.update();
    }
    const t = setTimeout(() => fit(null), 60);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, camera]);

  // camera commands (zoom extents / selected / saved view)
  useEffect(() => {
    if (request.id === lastRequest.current) return;
    lastRequest.current = request.id;
    if (request.action === "extents") fit(null);
    else if (request.action === "selected") {
      const sel = useView.getState().selection;
      const bodies = sel.filter((id) => groups.current.has(id));
      fit(bodies.length ? bodies : null);
    } else if (request.action === "saved" && request.saved && active && !ortho) {
      camera.position.set(...request.saved.position);
      controls.current?.target.set(...request.saved.target);
      controls.current?.update();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request]);

  // expose the perspective camera so SaveView can read it
  useEffect(() => {
    if (!active || ortho) return;
    const handler = () => {
      const name = window.prompt("Name for this view:", `View ${useView.getState().savedViews.length + 1}`);
      if (!name || !controls.current) return;
      const p = camera.position;
      const t = controls.current.target;
      useView.getState().set({
        savedViews: [...useView.getState().savedViews.filter((v) => v.name !== name), { name, position: [p.x, p.y, p.z], target: [t.x, t.y, t.z] }],
      });
    };
    window.addEventListener("calflab:save-view", handler);
    return () => window.removeEventListener("calflab:save-view", handler);
  }, [active, ortho, camera]);

  return (
    <>
      {ortho ? (
        <OrthographicCamera makeDefault near={1} far={50000} zoom={0.6} />
      ) : (
        <PerspectiveCamera makeDefault fov={35} near={5} far={60000} />
      )}
      <OrbitControls
        ref={controls}
        makeDefault
        enableRotate={!ortho}
        enableDamping={false}
        zoomSpeed={1.1}
        mouseButtons={buttons(nav, ortho)}
      />
    </>
  );
}
