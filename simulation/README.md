# Компоненты симуляции

- Плагин и модель IRIS: [osrf/vehicle_gateway](https://github.com/osrf/vehicle_gateway),
  commit `cfe101602d84192286de2626650cda1a8e81f971`, Apache-2.0 (`plugin/LICENSE`).
- Мир и адаптация Harmonic: [Jinyao-Chen/bf_sitl](https://github.com/Jinyao-Chen/bf_sitl),
  commit `dc5bec4218fdfe3c6b185d3b6a0da753f32ff5cd`.
- Betaflight: [betaflight/betaflight](https://github.com/betaflight/betaflight),
  commit `a12049c58c4d9542dab18a803dad4608d2c1cc46`, GPL-3.0 (`vendor/betaflight-LICENSE`).

Сборка: `./scripts/build_gazebo.sh` из корня проекта.
Рабочие файлы находятся в `.runtime/gazebo/`.
