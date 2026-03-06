/************************************
 * PARENT LIVE MAP (READ ONLY)
 ************************************/

var map = L.map("map").setView([19.0760, 72.8777], 13);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap"
}).addTo(map);

var busMarker = null;
var routeLayers = [];

/* -------------------------------
   CUSTOM BUS ICON
-------------------------------- */
var busIcon = L.icon({
    iconUrl: "/static/images/bus.png",
    iconSize: [50, 50],
    iconAnchor: [25, 25]
});

/* -------------------------------
   FETCH BUS LOCATION (LIVE)
-------------------------------- */
function fetchBusLocation() {

    fetch(`/parent/bus-location/${busId}`)
        .then(res => res.json())
        .then(data => {

            if (!data || !data.latitude || !data.longitude) return;

            const latLng = [data.latitude, data.longitude];

            if (!busMarker) {
                busMarker = L.marker(latLng, { icon: busIcon }).addTo(map);
                map.setView(latLng, 16);
            } else {
                busMarker.setLatLng(latLng);
            }
        })
        .catch(err => console.error("Location fetch error", err));
}

/* -------------------------------
   LOAD ROUTE + STOPS
-------------------------------- */
function loadRoute() {

    fetch(`/parent/bus-route/${busId}`)
        .then(res => res.json())
        .then(stops => {

            if (!Array.isArray(stops) || stops.length < 2) {
                console.warn("Not enough stops for route");
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
                    radius: 6,
                    color: "#0d6efd",
                    fillColor: "#0d6efd",
                    fillOpacity: 1
                })
                .addTo(map)
                .bindTooltip(`${i + 1}. ${s.name}`, {
                    permanent: true,
                    direction: "top",
                    offset: [0, -8]
                });
            });

            // Build OSRM coordinate string
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
                        console.warn("No route returned");
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
                .catch(err => console.error("Routing error", err));

        })
        .catch(err => console.error("Route fetch error", err));
}

/* -------------------------------
   INIT
-------------------------------- */
loadRoute();
fetchBusLocation();
setInterval(fetchBusLocation, 5000);
