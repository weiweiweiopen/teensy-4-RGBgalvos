# teensy-4-RGBgalvos

Teensy 4.x RGB laser galvo controller experiments for Wise Mouse Culture.

This project explores Teensy 4.x based multi-channel audio / DAC style control for RGB laser galvos, with companion Max/MSP and Python tooling for path generation and laser drawing workflows.

## Inspiration

This work is inspired by alex6679's Teensy 4 USB audio work:

- https://github.com/alex6679/teensy-4-usbAudio

The goal here is not to copy that project directly, but to extend the idea toward RGB galvo / laser-control workflows using Teensy 4.x hardware.

## Repository contents

Current public contents may include:

- `kicad/` — KiCad schematic / PCB project files when available.
- `laser_galvo_teensy/` — Teensy / Arduino sketch when available.
- `python/` — helper scripts for path generation and optimization.
- `max/` — Max/MSP patches when available.

Some local iCloud files were not readable from the build machine at the first publication pass, so hardware/firmware assets may be completed in a later commit after local file sync finishes.

## License

MIT License. See [`LICENSE`](LICENSE).
