# Roadmap

Three milestones, each usable on its own: **M1** discovery bridge (replaces hass-dingz), **M2** provisioning via CLI, **M3** web UI.

Status: ✅ done · 🔄 in progress · ⏳ open

## Phase 0 – Verification on real devices ✅ (remainder open)

- ✅ HTTP API (FW 2.4.3) read, anonymised in `tests/fixtures/http/`
- ✅ mDNS: `_http._tcp` with TXT records incl. MQTT `id` (`tests/fixtures/mdns_http_tcp.txt`)
- ✅ `mqtt.uri` format read (`mqtt://user:pass@host`)
- ✅ MQTT capture of light, LED, buttons, status dump → `tests/fixtures/mqtt/`
- ✅ Energy unit (Ws → kWh), LED colour from HA
- ✅ Temperature: status dump floors to whole degrees → temperature filter in the bridge (`filters.py`), start value from HTTP
- ✅ Energy counter not persistent across reboots (handled by `total_increasing`)
- ⏳ Motor, input, multi-click (no matching devices / cannot be simulated)
- ⏳ Write format of `POST /services_config`, reboot needed?, `/login`, `/protected` (test needs approval)

## M1 – Discovery bridge

### Phase 1 – Project skeleton ✅
`pyproject.toml` (extras `dev`, `ui`), ruff, pytest, `.gitignore`, README.

### Phase 2 – `topics.py` ✅
`parse_topic()` → `TopicInfo`, robust rejection of foreign topics, topic builders.

### Phase 3 – `discovery.py` ✅
`DeviceState.observe()` collects channels; `build_device_config()` creates the device discovery (light/template, switch, cover incl. tilt, LED, event, PIR with `off_delay`, input, sensors, power/energy). Removed channels are reported as `{"platform": …}`. Templates are tested against the documented and captured payloads.

### Phase 4 – `bridge.py` + CLI ✅
Incl. `--dry-run`, ID/name prefixes and HTTP enrichment (`device_api.py`). Verified against the real broker.
- Config from CLI/env (CLI wins), logging
- Subscribe `dingz/#` + `homeassistant/device/+/config` (own prefix only)
- Debounce per device (~2 s), publish only on change, retained, QoS 1
- Cleanup: devices without retained `dingz/<id>/…` → empty retained payload; offline ≠ removed
- Reconnect with back-off, clean shutdown

### Phase 5 – Packaging & field test 🔄
✅ `Dockerfile` (one image for standalone and add-on), `docker-compose.yml` + `.env.example`, `addon/` (config, translations, DOCS), `repository.yaml`, CI (tests + multi-arch images to ghcr on tags, lowercase owner).
✅ Test devices with prefix `dingztest`/`TEST ` in HA, light/LED verified from HA.
✅ Docker build arm64 and amd64 (83 MB, prebuilt wheels only); bridge dry run and MQTT scan tested in the container as user 1000.
⏳ Publish the repository, first release, install the add-on, replace hass-dingz.

## M2 – Provisioning CLI

### Phase 6 – `device_api.py` ✅
Enrichment, `status()` (secrets masked), `wifi()`, `set_mqtt()` with verification. ⏳ Confirm the write format on a device, `/login`.

### Phase 7 – `scan.py` + subcommands ✅
mDNS + `announce` + subnet sweep, deduplication by MAC/IP/MQTT ID. `scan`, `status [--wifi]`, `set-mqtt` (with confirmation). Tested against the real devices (mDNS and sweep find all 4).

## M3 – Web UI

### Phase 8 – `web.py` ✅
aiohttp + static HTML/JS. Device list (incl. “in HA”, link to the device web interface, WLAN column, MQTT activity marker), details, “set MQTT”, “rescan” (optional subnet), repository link and update check. Auth: ingress peer or `127.0.0.1` / mandatory basic auth; CSRF header; scanned hosts only.

### Phase 8b – Extensions ✅
Web UI bilingual (en/de), WLAN column and MQTT activity marker, link to the device web interface, update check. MQTT over TLS (own CA, client certificates; tested against a Mosquitto with own CA: rejected without CA, connects with `--tls-insecure`; ⏳ full verification with the CA file pending). Multi-arch Docker image `ghcr.io/probieri/dingz-ha-bridge` (non-root user `app`) via CI job `image`; add-on images (root) via `addon-image`. Temperature filter.

### Phase 9 – Wrap-up 🔄
✅ Renamed to dingz HA Bridge (`dingz_ha_bridge` / `dingz-ha-bridge`). ✅ Documentation in `docs/` (English), README in English and German. ⏳ First tag/release.

## Risks

| Risk | Mitigation |
|---|---|
| FW 2.x behaviour differs from the docs | fixtures from real devices, extend phase 0 before each phase |
| Inconsistent motor payload | templates accept `motion` and `state` |
| Orphaned configs/duplicate entities | only touch the own prefix; delete only when retained data is missing |
| mDNS in containers | host networking, fallback sources, clear log message |
| Broker credentials stored on the dingz | dedicated broker user + ACL (docs/*/security.md); the bridge never logs or shows passwords |
