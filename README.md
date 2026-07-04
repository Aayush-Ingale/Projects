# Home Server

A collection of scripts, configs, and projects for my home server / homelab setup.

## Overview

This repo is where I keep the code and configuration I use to run and maintain my home server — things like service configs, automation scripts, monitoring setups, and one-off tools I build along the way.

## Structure

```
.
├── docker/         # Docker Compose files and service configs
├── scripts/        # Utility and automation scripts
├── configs/        # Dotfiles, system configs, service configs
├── projects/       # Standalone projects/apps running on the server
└── docs/           # Notes, setup guides, troubleshooting
```

> Folder layout is a work in progress and will evolve as the repo grows.

## Hardware

- **Device:**
- **CPU:**
- **RAM:**
- **Storage:**
- **OS:**

## Services Running

| Service | Purpose | Port |
|---|---|---|
|  |  |  |
|  |  |  |

## Getting Started

Most services are managed via Docker Compose. To spin up a service:

```bash
cd docker/<service-name>
docker compose up -d
```

## Notes

- This is a personal, evolving repo — expect changes, experiments, and the occasional mess.
- Secrets, API keys, and `.env` files are **not** committed. See `.env.example` files where applicable.

## License

MIT (or update as you prefer)
