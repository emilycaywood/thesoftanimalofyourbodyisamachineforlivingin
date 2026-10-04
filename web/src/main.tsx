import React from "react";
import ReactDOM from "react-dom/client";
import * as THREE from "three";
import "./index.css";
import { App } from "./App";

// The scene is Z-up like Rhino and the simulator (ADR-005).
THREE.Object3D.DEFAULT_UP.set(0, 0, 1);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
