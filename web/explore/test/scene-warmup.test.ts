import assert from "node:assert/strict";
import test from "node:test";
import { BoxGeometry, Group, InstancedMesh, MeshBasicMaterial, PerspectiveCamera, Scene } from "three/webgpu";
import { warmScene } from "../src/scene-warmup.ts";

test("startup compiles hidden and zero-count LODs, then restores culling, visibility and counts", async () => {
  const scene = new Scene(), group = new Group(), mesh = new InstancedMesh(new BoxGeometry(), new MeshBasicMaterial(), 10);
  scene.add(group);
  group.add(mesh);
  group.visible = mesh.visible = false;
  mesh.count = 0;
  let rendered = false;
  const renderer = { render() { rendered = true; assert.equal(mesh.count, 1); }, async compileAsync() {
    assert.equal(group.visible, true);
    assert.equal(mesh.visible, true);
    assert.equal(mesh.frustumCulled, false);
    assert.equal(mesh.count, 1);
  } };
  await warmScene(renderer, scene, new PerspectiveCamera());
  assert.equal(rendered, true);
  assert.equal(group.visible, false);
  assert.equal(mesh.visible, false);
  assert.equal(mesh.frustumCulled, true);
  assert.equal(mesh.count, 0);
  await assert.rejects(warmScene({ render() {}, async compileAsync() { throw Error("compile failed"); } }, scene, new PerspectiveCamera()), /compile failed/);
  assert.equal(group.visible, false);
  assert.equal(mesh.visible, false);
  assert.equal(mesh.count, 0);
  mesh.geometry.dispose();
  mesh.material.dispose();
});

test("an empty scene still completes startup compilation", async () => {
  let called = 0;
  await warmScene({ render() {}, async compileAsync() { called++; } }, new Scene(), new PerspectiveCamera());
  assert.equal(called, 1);
});
