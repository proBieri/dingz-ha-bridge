# One Dockerfile for the standalone image and the Home Assistant add-on (amd64, aarch64).
# In the add-on the settings come from the Supervisor (see dingz_ha_bridge/addon.py).
#
# The image runs as the unprivileged user "app" (UID 1000). The add-on images are built
# with --build-arg RUN_AS=0 because the add-on reads Supervisor files below /data.

FROM python:3.12-alpine3.22 AS build
# Only needed if a dependency has no musllinux wheel for the target arch.
RUN apk add --no-cache build-base
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY dingz_ha_bridge ./dingz_ha_bridge
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[ui]"

FROM python:3.12-alpine3.22
ARG BUILD_VERSION=dev
ARG RUN_AS=1000
LABEL org.opencontainers.image.title="dingz-ha-bridge" \
      org.opencontainers.image.description="Expose dingz switches to Home Assistant via MQTT discovery" \
      org.opencontainers.image.source="https://github.com/proBieri/dingz-ha-bridge" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      io.hass.type="addon" \
      io.hass.version="${BUILD_VERSION}"
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels dingz-ha-bridge[ui] \
    && rm -rf /wheels \
    && adduser -D -H -u 1000 -s /sbin/nologin app
ENV PYTHONUNBUFFERED=1
USER ${RUN_AS}
ENTRYPOINT ["dingz-ha-bridge"]
CMD ["run"]
