/**
 * Three.js Pro 3D Holographic Viewport.
 * Renders fluidly-interpolated 3D skeletal wireframe, head volume, torso plane,
 * dynamic ground projection shadow, and concentric metric distance rings.
 */
import * as THREE from 'three';

const POSE_CONNECTIONS = [
  [0, 11], [0, 12],       // Neck / Head
  [11, 12],               // Shoulders
  [11, 13], [13, 15],     // Left Arm
  [12, 14], [14, 16],     // Right Arm
  [11, 23], [12, 24],     // Torso Sides
  [23, 24],               // Hips
  [23, 25], [25, 27],     // Left Leg
  [24, 26], [26, 28]      // Right Leg
];

export class Hologram3DView {
  constructor(containerElement) {
    this.container = containerElement;
    this.width = containerElement.clientWidth || 300;
    this.height = containerElement.clientHeight || 200;

    // Scene, Camera, Renderer
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, this.width / this.height, 0.1, 100);
    this.camera.position.set(0, 0.35, 3.2);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    // Group for the 3D subject
    this.subjectGroup = new THREE.Group();
    this.scene.add(this.subjectGroup);

    // Skeleton joints, target positions (for lerp), and bones
    this.jointMeshes = [];
    this.targetPositions = [];
    this.boneLines = [];

    // Anatomical Volumes
    this.headWireframe = null;
    this.groundShadow = null;
    this.directionArrow = null;

    // Orbit control state (manual mouse dragging)
    this.isDragging = false;
    this.prevMouse = { x: 0, y: 0 };
    this.rotation = { x: 0.1, y: 0.0 };

    this._initScene();
    this._initEventListeners();
    this._animate();
  }

  _initScene() {
    // 1. Ambient & Directional Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4);
    this.scene.add(ambientLight);

    const whiteLight = new THREE.PointLight(0xffffff, 2.5, 10);
    whiteLight.position.set(2, 3, 2);
    this.scene.add(whiteLight);

    // 2. Coordinate Floor Grid
    const gridHelper = new THREE.GridHelper(3.6, 14, 0x52525b, 0x27272a);
    gridHelper.position.y = -0.9;
    this.scene.add(gridHelper);

    // Concentric Metric Range Rings on floor (1m, 2m, 3m)
    [0.7, 1.4, 2.1].forEach((r) => {
      const ringGeo = new THREE.RingGeometry(r - 0.005, r + 0.005, 32);
      const ringMat = new THREE.MeshBasicMaterial({ color: 0x3f3f46, side: THREE.DoubleSide });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = Math.PI / 2;
      ring.position.y = -0.899;
      this.scene.add(ring);
    });

    // 3. Ground Projection Shadow Ring
    const shadowGeo = new THREE.RingGeometry(0.18, 0.22, 24);
    const shadowMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide, transparent: true, opacity: 0.45 });
    this.groundShadow = new THREE.Mesh(shadowGeo, shadowMat);
    this.groundShadow.rotation.x = Math.PI / 2;
    this.groundShadow.position.y = -0.898;
    this.scene.add(this.groundShadow);

    // 4. Directional Heading Arrow
    const dir = new THREE.Vector3(0, 0, -1);
    const origin = new THREE.Vector3(0, -0.85, 0);
    this.directionArrow = new THREE.ArrowHelper(dir, origin, 0.6, 0xffffff, 0.12, 0.06);
    this.scene.add(this.directionArrow);

    // 5. Build Default Skeleton & Volumes
    this._buildDefaultSkeleton();
  }

  _buildDefaultSkeleton() {
    while (this.subjectGroup.children.length > 0) {
      this.subjectGroup.remove(this.subjectGroup.children[0]);
    }
    this.jointMeshes = [];
    this.targetPositions = [];
    this.boneLines = [];

    // Joint geometry
    const sphereGeo = new THREE.SphereGeometry(0.038, 16, 16);
    const jointMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.2
    });

    for (let i = 0; i < 33; i++) {
      const mesh = new THREE.Mesh(sphereGeo, jointMat);
      mesh.visible = false;
      this.subjectGroup.add(mesh);
      this.jointMeshes.push(mesh);
      this.targetPositions.push(new THREE.Vector3(0, 0, 0));
    }

    // Bone Line Segments
    const lineMat = new THREE.LineBasicMaterial({
      color: 0xffffff,
      linewidth: 1.5,
      transparent: true,
      opacity: 0.65
    });

    POSE_CONNECTIONS.forEach(() => {
      const geo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(0, 0, 0)
      ]);
      const line = new THREE.Line(geo, lineMat);
      line.visible = false;
      this.subjectGroup.add(line);
      this.boneLines.push(line);
    });

    // Head Volume Wireframe Sphere
    const headGeo = new THREE.SphereGeometry(0.12, 8, 8);
    const headMat = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      wireframe: true,
      transparent: true,
      opacity: 0.35
    });
    this.headWireframe = new THREE.Mesh(headGeo, headMat);
    this.headWireframe.visible = false;
    this.subjectGroup.add(this.headWireframe);
  }

  updateFromLandmarks(landmarks3d, yawDeg = 0) {
    if (!landmarks3d || landmarks3d.length === 0) return;

    let hipCx = 0, hipCy = 0, hipCz = 0;
    if (landmarks3d.length > 24) {
      hipCx = (landmarks3d[23].x + landmarks3d[24].x) / 2.0;
      hipCy = (landmarks3d[23].y + landmarks3d[24].y) / 2.0;
      hipCz = (landmarks3d[23].z + landmarks3d[24].z) / 2.0;
    }

    // Update target positions for lerp
    landmarks3d.forEach((lm, idx) => {
      if (idx < this.targetPositions.length) {
        if (lm.visibility > 0.25) {
          this.targetPositions[idx].set(
            -(lm.x - hipCx) * 1.5,
            -(lm.y - hipCy) * 1.5,
            -(lm.z - hipCz) * 1.5
          );
          this.jointMeshes[idx].visible = true;
        } else {
          this.jointMeshes[idx].visible = false;
        }
      }
    });

    // Update Head wireframe target
    if (this.headWireframe && landmarks3d.length > 0) {
      const noseTarget = this.targetPositions[0];
      this.headWireframe.position.copy(noseTarget);
      this.headWireframe.visible = true;
    }

    // Update Orientation arrow
    if (this.directionArrow) {
      const rad = (yawDeg * Math.PI) / 180;
      const dirVec = new THREE.Vector3(Math.sin(rad), 0, -Math.cos(rad));
      this.directionArrow.setDirection(dirVec);
    }
  }

  _initEventListeners() {
    this.container.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.prevMouse = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isDragging) return;
      const deltaX = e.clientX - this.prevMouse.x;
      const deltaY = e.clientY - this.prevMouse.y;
      this.rotation.y += deltaX * 0.01;
      this.rotation.x += deltaY * 0.01;
      this.rotation.x = Math.max(-Math.PI / 4, Math.min(Math.PI / 4, this.rotation.x));
      this.prevMouse = { x: e.clientX, y: e.clientY };
    });

    this.container.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.camera.position.z = Math.max(1.2, Math.min(5.0, this.camera.position.z + e.deltaY * 0.004));
    });
  }

  _animate() {
    requestAnimationFrame(() => this._animate());

    // Gentle auto-rotation when not dragging
    if (!this.isDragging) {
      this.rotation.y += 0.004;
    }

    this.subjectGroup.rotation.y = this.rotation.y;
    this.subjectGroup.rotation.x = this.rotation.x;

    // Smooth Lerp Interpolation for joint meshes (elimates jitter)
    const lerpFactor = 0.35;
    for (let i = 0; i < this.jointMeshes.length; i++) {
      if (this.jointMeshes[i].visible) {
        this.jointMeshes[i].position.lerp(this.targetPositions[i], lerpFactor);
      }
    }

    // Update connecting bone lines
    POSE_CONNECTIONS.forEach(([iA, iB], lineIdx) => {
      if (lineIdx < this.boneLines.length && iA < this.jointMeshes.length && iB < this.jointMeshes.length) {
        const meshA = this.jointMeshes[iA];
        const meshB = this.jointMeshes[iB];
        const line = this.boneLines[lineIdx];

        if (meshA.visible && meshB.visible) {
          line.visible = true;
          const posAttr = line.geometry.attributes.position;
          posAttr.setXYZ(0, meshA.position.x, meshA.position.y, meshA.position.z);
          posAttr.setXYZ(1, meshB.position.x, meshB.position.y, meshB.position.z);
          posAttr.needsUpdate = true;
        } else {
          line.visible = false;
        }
      }
    });

    this.renderer.render(this.scene, this.camera);
  }

  resize() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (w > 0 && h > 0) {
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h);
    }
  }
}
