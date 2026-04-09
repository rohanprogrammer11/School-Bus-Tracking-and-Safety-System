let map;
let busMarker = null;
let busIcon;
let routeLayers = [];

// ✅ STORE ROUTE COORDS GLOBALLY
let routeCoords = [];

// ✅ AUTO FOLLOW FLAG
let autoFollow = true;

function initMap() {
    map = L.map("map").setView([20.5937, 78.9629], 5);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap"
    }).addTo(map);

    busIcon = L.icon({
        iconUrl: "/static/images/bus.png",
        iconSize: [40, 40],
        iconAnchor: [20, 40]
    });

    // ❗ stop auto-follow when user moves map
    map.on('dragstart', () => {
        autoFollow = false;
    });

    loadRoadRoute();
}

/* =========================
   LOAD ROAD ROUTE (SEGMENTS)
========================= */
function loadRoadRoute() {
    fetch(`/org/api/bus-route/${busId}`, { credentials: "same-origin" })
        .then(res => res.json())
        .then(stops => {

            if (!Array.isArray(stops) || stops.length < 2) {
                console.warn("⚠️ Not enough stops for routing");
                return;
            }

            const bounds = [];

            routeLayers.forEach(layer => map.removeLayer(layer));
            routeLayers = [];

            stops.forEach((s, i) => {

                if (!s.latitude || !s.longitude) return;

                const latLng = [s.latitude, s.longitude];
                bounds.push(latLng);

                L.circleMarker(latLng, {
                    radius: 7,
                    color: "#0d6efd",
                    fillColor: "#0d6efd",
                    fillOpacity: 1
                })
                .addTo(map)
                .bindTooltip(`${i + 1}. ${s.name}`, {
                    permanent: true,
                    direction: "top",
                    offset: [0, -8],
                    className: "stop-label"
                });
            });

            const coordinates = stops
                .filter(s => s.latitude && s.longitude)
                .map(s => `${s.longitude},${s.latitude}`)
                .join(";");

            const osrmUrl =
                `https://router.project-osrm.org/route/v1/driving/` +
                `${coordinates}?overview=full&geometries=geojson`;

            fetch(osrmUrl)
                .then(res => res.json())
                .then(data => {

                    if (!data.routes || !data.routes.length) {
                        console.warn("OSRM returned no route");
                        return;
                    }

                    const coords = data.routes[0].geometry.coordinates.map(
                        c => [c[1], c[0]]
                    );

                    routeCoords = coords;

                    const line = L.polyline(coords, {
                        color: "#0d6efd",
                        weight: 5
                    }).addTo(map);

                    routeLayers.push(line);

                    map.fitBounds(bounds, { padding: [40, 40] });
                })
                .catch(err => console.error("OSRM error:", err));

        })
        .catch(err => console.error("Route load error:", err));
}

/* =========================
   SNAP TO ROUTE
========================= */
function getClosestPointOnRoute(lat, lng, routeCoords) {
    let minDist = Infinity;
    let closest = null;

    routeCoords.forEach(coord => {
        const d = Math.sqrt(
            Math.pow(coord[0] - lat, 2) +
            Math.pow(coord[1] - lng, 2)
        );

        if (d < minDist) {
            minDist = d;
            closest = coord;
        }
    });

    return closest;
}

/* =========================
   SMOOTH ANIMATION
========================= */
function easeInOut(t) {
    return t < 0.5
        ? 2 * t * t
        : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

function animateMarker(marker, from, to, duration = 1500) {
    const start = performance.now();

    function animate(time) {
        const progress = Math.min((time - start) / duration, 1);
        const eased = easeInOut(progress);

        const lat = from[0] + (to[0] - from[0]) * eased;
        const lng = from[1] + (to[1] - from[1]) * eased;

        marker.setLatLng([lat, lng]);

        if (progress < 1) {
            requestAnimationFrame(animate);
        }
    }

    requestAnimationFrame(animate);
}

/* =========================
   LIVE BUS LOCATION
========================= */
let lastLatLng = null;

function fetchBusLocation() {

    fetch(`/org/api/bus-location/${busId}?t=${Date.now()}`, {
        credentials: "same-origin",
        cache: "no-store"
    })
    .then(res => res.json())
    .then(data => {

        if (!data || !data.latitude || !data.longitude) return;

        let lat = data.latitude;
        let lng = data.longitude;

        let snapped = null;

        if (routeCoords.length > 0) {
            snapped = getClosestPointOnRoute(lat, lng, routeCoords);
        }

        const latLng = snapped || [lat, lng];

        // filter jump
        if (lastLatLng) {
            const distance = map.distance(lastLatLng, latLng);
            if (distance > 100) return;
        }

        lastLatLng = latLng;

        if (!busMarker) {
            busMarker = L.marker(latLng, { icon: busIcon }).addTo(map);
            map.setView(latLng, 16);
        } else {
            const current = busMarker.getLatLng();
            const from = [current.lat, current.lng];

            animateMarker(busMarker, from, latLng, 1500);

            // ✅ AUTO FOLLOW
            if (autoFollow) {
                map.panTo(latLng, {
                    animate: true,
                    duration: 1
                });
            }
        }

    })
    .catch(err => console.error("GPS error:", err));
}

/* =========================
   AUTO REFRESH
========================= */
setInterval(fetchBusLocation, 2000);