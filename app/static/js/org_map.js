let map;
let busMarker = null;
let busIcon;
let routeLayers = [];

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

            // Clear old route
            routeLayers.forEach(layer => map.removeLayer(layer));
            routeLayers = [];

            // Draw stop markers
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

            // Build coordinate string
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
   LIVE BUS LOCATION
========================= */
function fetchBusLocation() {

    fetch(`/org/api/bus-location/${busId}?t=${Date.now()}`, {
        credentials: "same-origin",
        cache: "no-store"
    })
    .then(res => res.json())
    .then(data => {

        console.log("ORG GPS:", data.latitude, data.longitude, data.event_time);

        if (!data || !data.latitude || !data.longitude) return;

        const latLng = [data.latitude, data.longitude];

        if (!busMarker) {
            busMarker = L.marker(latLng, {
                icon: busIcon
            }).addTo(map);

            map.setView(latLng, 16);
        } else {
            busMarker.setLatLng(latLng);
        }

    })
    .catch(err => console.error("Org map GPS error:", err));
}
