const socket = io(window.location.origin); // Use full origin in case of ngrok or external IP
let markers = {};

socket.on('update_marker', data => {
    if (markers[data.id]) {
        markers[data.id].setLatLng([data.lat, data.lng])
            .bindPopup(`
                <b>Bus Number:</b> ${data.new_bus_number || 'Unknown'}<br>
                <b>Route Name:</b> ${data.new_route_name || 'Unknown'}<br>
                <b>Current Location:</b> ${data.name}
            `);
    }
});

socket.on('name_updated', data => {
    if (markers[data.id]) {
        markers[data.id].bindPopup(`
            <b>Bus Number:</b> ${data.new_bus_number}<br>
            <b>Route Name:</b> ${data.new_route_name}<br>
            <b>Current Location:</b> ${data.new_name}
        `);
        alert('Bus details updated and locked.');
    }
});
