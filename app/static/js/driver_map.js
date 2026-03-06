/************************************
 * DRIVER LIVE MAP (OpenStreetMap)
 * File: app/static/js/driver_map.js
 ************************************/

console.log("Driver map JS loaded");

/* -------------------------------
   GLOBAL BUS LOCATION
-------------------------------- */
var busLat = null;
var busLng = null;

/* -------------------------------
   BASIC CHECK
-------------------------------- */
if (!("geolocation" in navigator)) {
    alert("Geolocation is not supported by this browser");
}

/* -------------------------------
   MAP INITIALIZATION
-------------------------------- */
var DEFAULT_LAT = 19.0760;   // fallback (Mumbai)
var DEFAULT_LNG = 72.8777;

var map = L.map("map").setView([DEFAULT_LAT, DEFAULT_LNG], 14);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors"
}).addTo(map);



/* -------------------------------
   BUS ICON
-------------------------------- */
var busIcon = L.icon({
    iconUrl: "/static/images/bus.png",
    iconSize: [45, 45],
    iconAnchor: [22, 22],
    popupAnchor: [0, -20]
});

/* -------------------------------
   MARKER & ACCURACY CIRCLE
-------------------------------- */
var marker = L.marker(
    [DEFAULT_LAT, DEFAULT_LNG],
    { icon: busIcon }
).addTo(map);

var accuracyCircle = null;

/* -------------------------------
   HAVERSINE DISTANCE
-------------------------------- */
function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371e3;
    const φ1 = lat1 * Math.PI / 180;
    const φ2 = lat2 * Math.PI / 180;
    const Δφ = (lat2 - lat1) * Math.PI / 180;
    const Δλ = (lon2 - lon1) * Math.PI / 180;

    const a = Math.sin(Δφ / 2) ** 2 +
        Math.cos(φ1) * Math.cos(φ2) *
        Math.sin(Δλ / 2) ** 2;

    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/* -------------------------------
   FIND BEST STOP (ROAD TIME)
-------------------------------- */
async function findBestStop(busLat, busLng, stops) {

    let best = null;
    let bestTime = Infinity;

    for (let s of stops) {

        const url =
            `https://router.project-osrm.org/route/v1/driving/` +
            `${busLng},${busLat};${s.lng},${s.lat}?overview=false`;

        const res = await fetch(url);
        const data = await res.json();

        if (data.routes && data.routes.length) {
            const time = data.routes[0].duration;

            if (time < bestTime) {
                bestTime = time;
                best = s;
            }
        }
    }

    return best;
}

/* -------------------------------
   DRAW ROUTE STOPS (IMPROVED)
-------------------------------- */
var routeLine = [];

if (Array.isArray(routeStops) && routeStops.length > 0) {

    routeStops.forEach((stop) => {

        const name = stop.stop_name;
        const lat = Number(stop.latitude);
        const lng = Number(stop.longitude);
        const order = stop.stop_order;

        if (!lat || !lng || lat === 0 || lng === 0) return;

        const point = [lat, lng];
        routeLine.push(point);

        // Custom stop icon
        const stopIcon = L.divIcon({
            className: "custom-stop-marker",
            html: `
                <div style="
                    background:#0d6efd;
                    color:#fff;
                    border-radius:50%;
                    width:28px;
                    height:28px;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    font-size:13px;
                    font-weight:bold;
                    border:2px solid white;
                    box-shadow:0 0 8px rgba(0,0,0,0.4);
                ">
                    ${order}
                </div>
            `,
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });

        const marker = L.marker(point, { icon: stopIcon })
            .addTo(map)
            .bindTooltip(
                `<b>${order}. ${name}</b>`,
                {
                    permanent: true,
                    direction: "top",
                    offset: [0, -15],
                    className: "stop-label"
                }
            );
    });
}

/* -------------------------------
   DRAW ROAD-BASED ROUTE (OSRM)
-------------------------------- */
function drawRoadRoute(points) {

    if (points.length < 2) return;

    const coords = points
        .map(p => `${p[1]},${p[0]}`)
        .join(";");

    const osrmUrl =
        `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`;

    fetch(osrmUrl)
        .then(res => res.json())
        .then(data => {

            if (!data.routes || !data.routes.length) return;

            const roadRoute = data.routes[0].geometry.coordinates
                .map(c => [c[1], c[0]]);

            L.polyline(roadRoute, {
                color: "blue",
                weight: 5
            }).addTo(map);

            map.fitBounds(roadRoute);
        })
        .catch(err => console.error("OSRM routing error", err));
}

drawRoadRoute(routeLine);

/* -------------------------------
   SUCCESS CALLBACK (GPS)
-------------------------------- */
function onLocationSuccess(position) {

    var lat = position.coords.latitude;
    var lng = position.coords.longitude;
    var accuracy = position.coords.accuracy;

    busLat = lat;
    busLng = lng;

    console.log("GPS:", lat, lng, "accuracy:", accuracy);

    // Snap bus to nearest point on route line
    if (routeLine.length > 0) {

        let nearestPoint = null;
        let minDist = Infinity;

        routeLine.forEach(point => {
            const d = haversine(lat, lng, point[0], point[1]);
            if (d < minDist) {
                minDist = d;
                nearestPoint = point;
            }
        });

        if (minDist < 50) {  // 50 meters tolerance
            marker.setLatLng(nearestPoint);
        } else {
            marker.setLatLng([lat, lng]);
        }

    } else {
        marker.setLatLng([lat, lng]);
    }


    map.setView([lat, lng], 16);

    if (accuracyCircle) map.removeLayer(accuracyCircle);

    accuracyCircle = L.circle([lat, lng], {
        radius: accuracy,
        color: "#0d6efd",
        fillColor: "#0d6efd",
        fillOpacity: 0.15
    }).addTo(map);

    /* -------------------------------
       FIND NEAREST & BEST STOP
    -------------------------------- */
    const nearbyStops = routeStops
        .map(s => ({
            name: s.stop_name,
            lat: s.latitude,
            lng: s.longitude,
            dist: haversine(busLat, busLng, s.latitude, s.longitude)
        }))
        .sort((a, b) => a.dist - b.dist)
        .slice(0, 3);

    findBestStop(busLat, busLng, nearbyStops)
        .then(best => {
            if (best) {
                console.log("Best next stop:", best.name);
            }
        });

    /* -------------------------------
       SEND LOCATION TO BACKEND
    -------------------------------- */
    fetch("/driver/location-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
             bus_id: busId,   // replace later dynamically
            latitude: lat,
            longitude: lng,
            accuracy: accuracy
        })
    }).catch(err => console.error("Location update failed:", err));
}

/* -------------------------------
   ERROR CALLBACK
-------------------------------- */
function onLocationError(error) {

    console.error("Geolocation error:", error);

    let message = "Unable to fetch location";

    switch (error.code) {
        case error.PERMISSION_DENIED:
            message = "Location permission denied.";
            break;
        case error.POSITION_UNAVAILABLE:
            message = "Location unavailable.";
            break;
        case error.TIMEOUT:
            message = "Location request timed out.";
            break;
    }

    alert(message);
}

/* -------------------------------
   START TRACKING
-------------------------------- */
navigator.geolocation.watchPosition(
    onLocationSuccess,
    onLocationError,
    {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0
    }
);

