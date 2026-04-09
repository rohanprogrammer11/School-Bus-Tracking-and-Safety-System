/************************************
 * PARENT LIVE MAP (READ ONLY)
 ************************************/

var map = L.map("map").setView([19.0760, 72.8777], 13);

L.tileLayer("https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap"
}).addTo(map);

var busMarker = null;
var routeLayers = [];

// ✅ STORE ROUTE COORDS
var routeCoords = [];

// ✅ LAST POSITION (for filter)
var lastLatLng = null;

// ✅ AUTO FOLLOW FLAG
var autoFollow = true;

/* -------------------------------
   CUSTOM BUS ICON
-------------------------------- */
var busIcon = L.icon({
    iconUrl: "/static/images/bus.png",
    iconSize: [50, 50],
    iconAnchor: [25, 25]
});

/* -------------------------------
   🔥 SMOOTH ANIMATION
-------------------------------- */
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

/* -------------------------------
   SNAP TO ROUTE
-------------------------------- */
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

/* -------------------------------
   FETCH BUS LOCATION (LIVE)
-------------------------------- */
function fetchBusLocation() {

    fetch(`/parent/bus-location/${busId}`)
        .then(res => res.json())
        .then(data => {

            if (!data || data.latitude == null || data.longitude == null) return;

            let lat = data.latitude;
            let lng = data.longitude;

            // ✅ SNAP TO ROAD
            let snapped = null;
            if (routeCoords.length > 0) {
                snapped = getClosestPointOnRoute(lat, lng, routeCoords);
            }

            const latLng = snapped || [lat, lng];

            // ✅ FILTER GPS JUMP
            if (lastLatLng) {
                const distance = map.distance(lastLatLng, latLng);

                if (distance > 100) {
                    console.warn("⚠️ Ignored GPS jump");
                    return;
                }
            }

            lastLatLng = latLng;

            if (!busMarker) {
                busMarker = L.marker(latLng, { icon: busIcon }).addTo(map);
                map.setView(latLng, 16);
            } else {
                const current = busMarker.getLatLng();
                const from = [current.lat, current.lng];
                const to = latLng;

                // ✅ SMOOTH MOVE
                animateMarker(busMarker, from, to, 1500);

                // ✅ AUTO FOLLOW MAP
                if (autoFollow) {
                    map.panTo(latLng, {
                        animate: true,
                        duration: 1
                    });
                }
            }
        })
        .catch(err => console.error("Location fetch error", err));
}

/* -------------------------------
   LOAD ROUTE + STOPS
-------------------------------- */
function loadRoute() {
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

                    // ✅ SAVE ROUTE FOR SNAPPING
                    routeCoords = coords;

                    const line = L.polyline(coords, {
                        color: "#0d6efd",
                        weight: 5
                    }).addTo(map);

                    routeLayers.push(line);

                })
                .catch(err => console.error("OSRM error:", err));

        })
        .catch(err => console.error("Route load error:", err));
}

/* -------------------------------
   STOP AUTO FOLLOW IF USER MOVES MAP
-------------------------------- */
map.on('dragstart', function () {
    autoFollow = false;
});

/* -------------------------------
   INIT
-------------------------------- */
loadRoute();
fetchBusLocation();
setInterval(fetchBusLocation, 2000);

/* -------------------------------
   MANUAL UPDATE FUNCTION
-------------------------------- */
function updateBusLocation(lat, lng) {
    const latLng = [lat, lng];

    if (!busMarker) {
        busMarker = L.marker(latLng, { icon: busIcon }).addTo(map);
    } else {
        const current = busMarker.getLatLng();
        const from = [current.lat, current.lng];

        animateMarker(busMarker, from, latLng, 1500);
    }

    map.setView(latLng, 16);
}