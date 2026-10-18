// SPDX-License-Identifier: GPL-3.0-or-later
// Optional presentation control, compiled against PySuperTuxKart2 v0.7.4 headers.
// Calls the native camera API. Never reads or changes kart controls or physics.
#include "graphics/camera/camera.hpp"
#include "modes/world.hpp"
#include <cmath>

// HUD-free rendering does not update the start signal's normal dismissal.
// Remove only that presentation node after the countdown has completed.
extern "C" int kart_camera_clear_start_signal() {
    auto* world = World::getWorld();
    if (!world || !world->getRaceGUI()) return 0;
    world->getRaceGUI()->removeReferee();
    return 1;
}

extern "C" int kart_camera_get(unsigned index, float* values) {
    if (!values || index >= Camera::getNumCameras()) return 0;
    auto* camera = Camera::getCamera(index)->getCameraSceneNode();
    const auto position = camera->getPosition();
    const auto target = camera->getTarget();
    values[0] = position.X; values[1] = position.Y; values[2] = position.Z;
    values[3] = target.X; values[4] = target.Y; values[5] = target.Z;
    values[6] = camera->getFOV();
    return 1;
}

extern "C" int kart_camera_set(unsigned index, const float* values) {
    if (!values || index >= Camera::getNumCameras()) return 0;
    for (unsigned i = 0; i < 7; ++i) if (!std::isfinite(values[i])) return 0;
    if (values[6] <= 0.1f || values[6] >= 3.0f) return 0;
    auto* camera = Camera::getCamera(index)->getCameraSceneNode();
    camera->setPosition({values[0], values[1], values[2]});
    camera->setTarget({values[3], values[4], values[5]});
    camera->setUpVector({0.0f, 1.0f, 0.0f});
    camera->setNearValue(0.15f);
    camera->setFOV(values[6]);
    camera->updateAbsolutePosition();
    return 1;
}
