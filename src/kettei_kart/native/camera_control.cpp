// SPDX-License-Identifier: GPL-3.0-or-later
// Camera capture and presentation, compiled against PySuperTuxKart2 v0.7.4 headers.
// Calls the native camera API. Never reads or changes kart controls or physics.
#include "graphics/camera/camera.hpp"
#include "graphics/irr_driver.hpp"
#include "karts/abstract_kart.hpp"
#include "karts/kart_model.hpp"
#include "ge_render_info.hpp"
#include "modes/world.hpp"
#include "race/race_manager.hpp"
#include "tracks/track.hpp"
#include <cmath>
#include <set>

extern "C" int kart_camera_count() { return Camera::getNumCameras(); }

extern "C" int kart_camera_info(unsigned index, float* values) {
    if (!values || index >= Camera::getNumCameras()) return 0;
    auto* camera = Camera::getCamera(index);
    values[0] = camera->getCameraSceneNode()->getAspectRatio();
    values[1] = camera->getKart()->getWorldKartId();
    values[2] = camera->getViewport().getWidth();
    values[3] = camera->getViewport().getHeight();
    return 1;
}

extern "C" int kart_camera_set_aspect(unsigned index, float aspect) {
    if (index >= Camera::getNumCameras() || !std::isfinite(aspect)
        || aspect < 0.1f || aspect > 10.0f) return 0;
    Camera::getCamera(index)->getCameraSceneNode()->setAspectRatio(aspect);
    return 1;
}

// Cosmetic replay only. Set the material hue after any saved player-profile
// preference has been applied by the engine; physics and controls are untouched.
extern "C" int kart_replay_set_hue(unsigned index, float hue) {
    auto* world = World::getWorld();
    if (!world || index >= RaceManager::get()->getNumPlayers() || !std::isfinite(hue)
        || hue <= 0.0f || hue > 1.0f) return 0;
    auto* kart = world->getPlayerKart(index);
    auto info = kart->getKartModel()->getRenderInfo();
    if (!info) return 0;
    info->setHue(hue);
    return 1;
}

extern "C" int kart_replay_label(unsigned index, const char* label) {
    auto* world = World::getWorld();
    if (!world || !label || index >= RaceManager::get()->getNumPlayers()) return 0;
    auto* kart = world->getPlayerKart(index);
    auto* node = kart->getNode();
    std::set<irr::scene::ISceneNode*> existing;
    for (unsigned i = 0; i < node->getChildren().size(); ++i)
        existing.insert(node->getChildren()[i]);
    kart->setOnScreenText(irr::core::stringw(label));
    for (unsigned i = 0; i < node->getChildren().size(); ++i) {
        auto* child = node->getChildren()[i];
        if (!existing.count(child)) child->setScale({0.12f, 0.12f, 0.12f});
    }
    return 1;
}

// Replay presentation only: change lighting after the original scene is loaded.
// Do not reload assets or alter scene objects, collision geometry or random state.
extern "C" int kart_replay_daylight() {
    auto* track = Track::getCurrentTrack();
    if (!track || !irr_driver) return 0;
    track->forceFogDisabled(true);
    irr_driver->setAmbientLight({90.f / 255.f, 110.f / 255.f, 120.f / 255.f});
    irr_driver->setSunColor({180.f / 255.f, 185.f / 255.f, 175.f / 255.f});
    return 1;
}

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
