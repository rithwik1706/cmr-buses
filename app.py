from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash
import random
import requests

app = Flask(__name__)
app.secret_key = 'your_secure_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///locations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager()
login_manager.init_app(app)

# Hardcoded admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("admin_password")

# User Model (For Flask-Login, without database interaction)
class User(UserMixin):
    def __init__(self, id):
        self.id = id

# Location Model
class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bus_number = db.Column(db.String(50), unique=True, nullable=False)
    route_name = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100))  # Geocoded place name
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    is_locked = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# Reverse geocoding function
def get_place_name(lat, lng):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
        headers = {'User-Agent': 'BusTrackerApp/1.0'}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('display_name', 'Unknown Location')
        return 'Unknown Location'
    except Exception:
        return 'Unknown Location'

# Login Route
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check against fixed admin credentials
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            user = User(id=username)  # Using the username as user ID
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'error')
    return render_template('login.html')

# Dashboard Route
@app.route('/dashboard')
@login_required
def dashboard():
    raw_locations = Location.query.all()
    locations = [{
        'id': loc.id,
        'bus_number': loc.bus_number,
        'route_name': loc.route_name,
        'name': loc.name,
        'lat': loc.lat,
        'lng': loc.lng,
        'is_locked': loc.is_locked
    } for loc in raw_locations]
    return render_template('dashboard.html', locations=locations)

# Logout Route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Driver Page Route
@app.route('/driver')
def driver():
    bus_id = request.args.get('id', default=1, type=int)
    return render_template('driver.html', bus_id=bus_id)

# API endpoint for location update
@app.route('/update_location', methods=['POST'])
def update_location():
    try:
        data = request.get_json()
        print("DEBUG: Received data from client ->", data)

        if not data or 'id' not in data or 'lat' not in data or 'lng' not in data:
            return 'Missing or invalid data', 400

        loc = Location.query.get(data['id'])
        if not loc:
            return 'Bus not found', 404

        # Validate coordinates
        lat = float(data['lat'])
        lng = float(data['lng'])

        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return 'Invalid coordinates', 400

        # Update values
        loc.lat = lat
        loc.lng = lng
        loc.name = get_place_name(lat, lng)
        db.session.commit()

        # Send update to all clients
        socketio.emit('update_marker', {
            'id': data['id'],
            'lat': lat,
            'lng': lng,
            'name': loc.name,
            'new_bus_number': loc.bus_number,
            'new_route_name': loc.route_name
        })

        return 'OK', 200

    except Exception as e:
        print("❌ ERROR in /update_location:", str(e))
        return f"Server Error: {str(e)}", 500

# Socket.IO - Location update
@socketio.on('location_update')
def handle_location_update(data):
    loc = Location.query.get(data['id'])
    if loc:
        if -90 <= data['lat'] <= 90 and -180 <= data['lng'] <= 180:
            loc.lat = data['lat']
            loc.lng = data['lng']
            loc.name = get_place_name(data['lat'], data['lng'])
            db.session.commit()
            socketio.emit('update_marker', {
                'id': data['id'],
                'lat': data['lat'],
                'lng': data['lng'],
                'name': loc.name,
                'new_bus_number': loc.bus_number,
                'new_route_name': loc.route_name
            }, broadcast=True)

# Socket.IO - Edit bus details
@socketio.on('edit_name')
def handle_edit_name(data):
    loc = Location.query.get(data['id'])
    if loc and not loc.is_locked:
        loc.bus_number = data['new_bus_number']
        loc.route_name = data['new_route_name']
        loc.name = get_place_name(loc.lat, loc.lng)
        loc.is_locked = True
        db.session.commit()
        socketio.emit('name_updated', {
            'id': data['id'],
            'new_name': loc.name,
            'new_bus_number': loc.bus_number,
            'new_route_name': loc.route_name,
            'is_locked': loc.is_locked
        }, broadcast=True)

# Initialize database
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        if Location.query.count() < 50:
            bus_data = [
                {"bus_number": "1", "route_name": "Rampally x Road", "lat": 17.6034937425493, "lng": 78.48695051843427},
                {"bus_number": "2", "route_name": "Nagaram", "lat": 17.6044937425493, "lng": 78.48795051843427},
                {"bus_number": "3", "route_name": "Kushaiguda", "lat": 17.6054937425493, "lng": 78.48895051843427},
                {"bus_number": "4", "route_name": "Charlapally", "lat": 17.6064937425493, "lng": 78.48995051843427},
                {"bus_number": "5", "route_name": "ECIL", "lat": 17.6074937425493, "lng": 78.49095051843427},
                {"bus_number": "6", "route_name": "ZTS", "lat": 17.6084937425493, "lng": 78.49195051843427},
                {"bus_number": "7", "route_name": "Malkajgiri", "lat": 17.6094937425493, "lng": 78.49295051843427},
                {"bus_number": "8", "route_name": "Boduuppal", "lat": 17.6104937425493, "lng": 78.49395051843427},
                {"bus_number": "9", "route_name": "Canaranagar", "lat": 17.6114937425493, "lng": 78.49495051843427},
                {"bus_number": "10", "route_name": "B.N.Reddy colony", "lat": 17.6124937425493, "lng": 78.49595051843427},
                {"bus_number": "11", "route_name": "L.B.Nagar", "lat": 17.6134937425493, "lng": 78.49695051843427},
                {"bus_number": "12", "route_name": "NTR NAGAR", "lat": 17.6144937425493, "lng": 78.49795051843427},
                {"bus_number": "13", "route_name": "Dilsuk Nagar", "lat": 17.6154937425493, "lng": 78.49895051843427},
                {"bus_number": "14", "route_name": "Karmanghat", "lat": 17.6164937425493, "lng": 78.49995051843427},
                {"bus_number": "15", "route_name": "Koti", "lat": 17.6174937425493, "lng": 78.50095051843427},
                {"bus_number": "16", "route_name": "Ramanthpur", "lat": 17.6184937425493, "lng": 78.50195051843427},
                {"bus_number": "17", "route_name": "Attapur", "lat": 17.6194937425493, "lng": 78.50295051843427},
                {"bus_number": "18", "route_name": "Lunger House", "lat": 17.6204937425493, "lng": 78.50395051843427},
                {"bus_number": "19", "route_name": "Yadagirigutta", "lat": 17.6214937425493, "lng": 78.50495051843427},
                {"bus_number": "20", "route_name": "Ashok Nagar", "lat": 17.6224937425493, "lng": 78.50595051843427},
                {"bus_number": "21", "route_name": "A.G.Colony", "lat": 17.6234937425493, "lng": 78.50695051843427},
    {"bus_number": "22", "route_name": "Bharath nagar", "lat": 17.6244937425493, "lng": 78.50795051843427},
    {"bus_number": "23", "route_name": "Sanath Nagar", "lat": 17.6254937425493, "lng": 78.50895051843427},
    {"bus_number": "24", "route_name": "KP METRO", "lat": 17.6264937425493, "lng": 78.50995051843427},
    {"bus_number": "25", "route_name": "Usha mullapudi arch", "lat": 17.6274937425493, "lng": 78.51095051843427},
    {"bus_number": "26", "route_name": "KPHB METRO STATION", "lat": 17.6284937425493, "lng": 78.51195051843427},
    {"bus_number": "27", "route_name": "KPHB Bus stop", "lat": 17.6294937425493, "lng": 78.51295051843427},
    {"bus_number": "28", "route_name": "Forum mall", "lat": 17.6304937425493, "lng": 78.51395051843427},
    {"bus_number": "29", "route_name": "Vasanth Nagar", "lat": 17.6314937425493, "lng": 78.51495051843427},
    {"bus_number": "30", "route_name": "Madinaguda", "lat": 17.6324937425493, "lng": 78.51595051843427},
    {"bus_number": "31", "route_name": "NEW MIG BHEL", "lat": 17.6334937425493, "lng": 78.51695051843427},
    {"bus_number": "32", "route_name": "LIG BHEL", "lat": 17.6344937425493, "lng": 78.51795051843427},
    {"bus_number": "33", "route_name": "Patancheru", "lat": 17.6354937425493, "lng": 78.51895051843427},
    {"bus_number": "34", "route_name": "Sanga Reddy", "lat": 17.6364937425493, "lng": 78.51995051843427},
]
            
            
            for bus in bus_data:
                db.session.add(Location(
                    bus_number=bus["bus_number"],
                    route_name=bus["route_name"],
                    name="Initial Location",
                    lat=bus["lat"],
                    lng=bus["lng"],
                    is_locked=False
                ))
            db.session.commit()

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
