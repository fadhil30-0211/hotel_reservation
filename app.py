from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date
from config import Config
from database import get_db_connection

app = Flask(__name__)
app.config.from_object(Config)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan masuk terlebih dahulu untuk mengakses halaman ini.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan masuk terlebih dahulu.', 'warning')
            return redirect(url_for('login'))
        if session.get('user_role') != 'admin':
            flash('Akses ditolak! Halaman ini hanya untuk Administrator.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('rupiah')
def rupiah_filter(value):
    try:
        return f"Rp {int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return f"Rp {value}"

def check_room_availability(room_id, check_in_date, check_out_date, exclude_reservation_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT id FROM reservations 
                WHERE room_id = %s 
                AND status IN ('pending', 'confirmed', 'checked_in')
                AND NOT (check_out <= %s OR check_in >= %s)
            """
            params = [room_id, check_in_date, check_out_date]
            if exclude_reservation_id:
                sql += " AND id != %s"
                params.append(exclude_reservation_id)

            cursor.execute(sql, params)
            overlapping = cursor.fetchone()
            return overlapping is None
    finally:
        conn.close()

# --- ROUTE PUBLIK & TAMU ---

@app.route('/')
def index():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM rooms WHERE status = 'available' LIMIT 3")
            featured_rooms = cursor.fetchall()
    except Exception as e:
        featured_rooms = []
    finally:
        conn.close()
    return render_template('index.html', featured_rooms=featured_rooms)

@app.route('/rooms')
def rooms():
    room_type = request.args.get('type', '').strip()
    max_price = request.args.get('max_price', '').strip()
    capacity = request.args.get('capacity', '').strip()

    sql = "SELECT * FROM rooms WHERE 1=1"
    params = []

    if room_type:
        sql += " AND room_type = %s"
        params.append(room_type)
    if max_price and max_price.isdigit():
        sql += " AND price_per_night <= %s"
        params.append(float(max_price))
    if capacity and capacity.isdigit():
        sql += " AND capacity >= %s"
        params.append(int(capacity))

    sql += " ORDER BY price_per_night ASC"

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rooms_list = cursor.fetchall()

            cursor.execute("SELECT DISTINCT room_type FROM rooms")
            all_types = [r['room_type'] for r in cursor.fetchall()]
    except Exception as e:
        rooms_list = []
        all_types = []
        flash(f'Gagal memuat data kamar: {str(e)}', 'danger')
    finally:
        conn.close()

    return render_template(
        'rooms.html',
        rooms=rooms_list,
        all_types=all_types,
        selected_type=room_type,
        selected_max_price=max_price,
        selected_capacity=capacity
    )

@app.route('/rooms/<int:room_id>')
def room_detail(room_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM rooms WHERE id = %s", (room_id,))
            room = cursor.fetchone()
            if not room:
                flash('Kamar tidak ditemukan.', 'warning')
                return redirect(url_for('rooms'))
    except Exception as e:
        flash(f'Terjadi kesalahan server: {str(e)}', 'danger')
        return redirect(url_for('rooms'))
    finally:
        conn.close()

    facilities_list = [f.strip() for f in room['facilities'].split(',')] if room['facilities'] else []
    today_str = date.today().isoformat()
    return render_template('room_detail.html', room=room, facilities_list=facilities_list, today_str=today_str)

@app.route('/book/<int:room_id>', methods=['GET', 'POST'])
@login_required
def book_room(room_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM rooms WHERE id = %s", (room_id,))
            room = cursor.fetchone()
            if not room:
                flash('Kamar tidak ditemukan.', 'danger')
                return redirect(url_for('rooms'))
    finally:
        conn.close()

    if room['status'] != 'available':
        flash('Kamar ini sedang tidak dapat dipesan.', 'warning')
        return redirect(url_for('room_detail', room_id=room_id))

    today_str = date.today().isoformat()

    if request.method == 'POST':
        check_in_str = request.form.get('check_in', '').strip()
        check_out_str = request.form.get('check_out', '').strip()

        if not check_in_str or not check_out_str:
            flash('Tanggal check-in dan check-out wajib diisi.', 'danger')
            return render_template('book_room.html', room=room, today_str=today_str)

        try:
            check_in_date = datetime.strptime(check_in_str, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Format tanggal tidak valid.', 'danger')
            return render_template('book_room.html', room=room, today_str=today_str)

        if check_in_date < date.today():
            flash('Tanggal check-in tidak boleh kurang dari hari ini.', 'danger')
            return render_template('book_room.html', room=room, today_str=today_str)

        if check_out_date <= check_in_date:
            flash('Tanggal check-out harus setelah tanggal check-in.', 'danger')
            return render_template('book_room.html', room=room, today_str=today_str)

        if not check_room_availability(room_id, check_in_str, check_out_str):
            flash('Maaf, kamar ini sudah dipesan pada tanggal tersebut. Silakan pilih tanggal lain.', 'danger')
            return render_template('book_room.html', room=room, today_str=today_str)

        nights = (check_out_date - check_in_date).days
        total_price = nights * float(room['price_per_night'])

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO reservations (user_id, room_id, check_in, check_out, total_price, status) 
                       VALUES (%s, %s, %s, %s, %s, 'pending')""",
                    (session['user_id'], room_id, check_in_str, check_out_str, total_price)
                )
                reservation_id = cursor.lastrowid

                cursor.execute(
                    """INSERT INTO payments (reservation_id, amount, payment_method, payment_status) 
                       VALUES (%s, %s, 'Transfer Bank', 'unpaid')""",
                    (reservation_id, total_price)
                )
                flash('Pemesanan kamar berhasil dibuat! Silakan tuntaskan pembayaran.', 'success')
                return redirect(url_for('pay_booking', booking_id=reservation_id))
        except Exception as e:
            flash(f'Gagal memproses pemesanan: {str(e)}', 'danger')
        finally:
            conn.close()

    return render_template('book_room.html', room=room, today_str=today_str)

@app.route('/my-bookings')
@login_required
def my_bookings():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT r.*, rm.room_number, rm.room_type, p.payment_status, p.id as payment_id
                FROM reservations r
                JOIN rooms rm ON r.room_id = rm.id
                LEFT JOIN payments p ON r.id = p.reservation_id
                WHERE r.user_id = %s
                ORDER BY r.created_at DESC
            """
            cursor.execute(sql, (session['user_id'],))
            bookings = cursor.fetchall()
    except Exception as e:
        bookings = []
        flash(f'Gagal memuat riwayat pemesanan: {str(e)}', 'danger')
    finally:
        conn.close()

    return render_template('my_bookings.html', bookings=bookings)

@app.route('/booking/<int:booking_id>')
@login_required
def booking_detail(booking_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT r.*, rm.room_number, rm.room_type, rm.facilities, u.name as guest_name, u.email as guest_email, p.payment_status, p.payment_method, p.payment_date
                FROM reservations r
                JOIN rooms rm ON r.room_id = rm.id
                JOIN users u ON r.user_id = u.id
                LEFT JOIN payments p ON r.id = p.reservation_id
                WHERE r.id = %s
            """
            cursor.execute(sql, (booking_id,))
            booking = cursor.fetchone()

            if not booking:
                flash('Data pemesanan tidak ditemukan.', 'danger')
                return redirect(url_for('my_bookings'))

            if booking['user_id'] != session['user_id'] and session.get('user_role') != 'admin':
                flash('Anda tidak memiliki izin untuk melihat pesanan ini.', 'danger')
                return redirect(url_for('my_bookings'))

    except Exception as e:
        flash(f'Terjadi kesalahan server: {str(e)}', 'danger')
        return redirect(url_for('my_bookings'))
    finally:
        conn.close()

    nights = (booking['check_out'] - booking['check_in']).days
    return render_template('booking_detail.html', booking=booking, nights=nights)

@app.route('/pay/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def pay_booking(booking_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT r.*, rm.room_number, rm.room_type, p.payment_status, p.amount
                FROM reservations r
                JOIN rooms rm ON r.room_id = rm.id
                LEFT JOIN payments p ON r.id = p.reservation_id
                WHERE r.id = %s AND r.user_id = %s
            """
            cursor.execute(sql, (booking_id, session['user_id']))
            booking = cursor.fetchone()

            if not booking:
                flash('Data pemesanan tidak ditemukan.', 'danger')
                return redirect(url_for('my_bookings'))

            if booking['payment_status'] == 'paid':
                flash('Pesanan ini sudah dibayar lunas.', 'info')
                return redirect(url_for('booking_detail', booking_id=booking_id))

            if request.method == 'POST':
                payment_method = request.form.get('payment_method', 'Transfer Bank')

                cursor.execute(
                    """UPDATE payments 
                       SET payment_status = 'paid', payment_method = %s, payment_date = NOW() 
                       WHERE reservation_id = %s""",
                    (payment_method, booking_id)
                )
                cursor.execute(
                    """UPDATE reservations 
                       SET status = 'confirmed' 
                       WHERE id = %s""",
                    (booking_id,)
                )
                flash('Pembayaran berhasil dikonfirmasi! Reservasi Anda telah terkonfirmasi.', 'success')
                return redirect(url_for('booking_detail', booking_id=booking_id))

    except Exception as e:
        flash(f'Gagal memproses pembayaran: {str(e)}', 'danger')
        return redirect(url_for('my_bookings'))
    finally:
        conn.close()

    return render_template('pay.html', booking=booking)

@app.route('/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM reservations WHERE id = %s AND user_id = %s",
                (booking_id, session['user_id'])
            )
            booking = cursor.fetchone()

            if not booking:
                flash('Pesanan tidak ditemukan.', 'danger')
                return redirect(url_for('my_bookings'))

            if booking['status'] in ['checked_in', 'checked_out']:
                flash('Pesanan yang sudah check-in/out tidak dapat dibatalkan.', 'warning')
                return redirect(url_for('my_bookings'))

            cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE id = %s", (booking_id,))
            cursor.execute("UPDATE payments SET payment_status = 'failed' WHERE reservation_id = %s", (booking_id,))
            flash('Pemesanan berhasil dibatalkan.', 'info')
    except Exception as e:
        flash(f'Gagal membatalkan pesanan: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('my_bookings'))

# --- AUTENTIKASI ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'tamu')

        if not name or not email or not password:
            flash('Semua kolom wajib diisi.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    flash('Email sudah terdaftar.', 'danger')
                    return redirect(url_for('register'))

                cursor.execute(
                    "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                    (name, email, hashed_password, role)
                )
                flash('Pendaftaran akun berhasil! Silakan masuk.', 'success')
                return redirect(url_for('login'))
        except Exception as e:
            flash(f'Terjadi kesalahan database: {str(e)}', 'danger')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email dan kata sandi wajib diisi.', 'danger')
            return redirect(url_for('login'))

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()

                if user and check_password_hash(user['password'], password):
                    session['user_id'] = user['id']
                    session['user_name'] = user['name']
                    session['user_email'] = user['email']
                    session['user_role'] = user['role']
                    flash(f'Selamat datang kembali, {user["name"]}!', 'success')
                    if user['role'] == 'admin':
                        return redirect(url_for('admin_dashboard'))
                    return redirect(url_for('dashboard'))
                else:
                    flash('Email atau kata sandi tidak cocok.', 'danger')
        except Exception as e:
            flash(f'Terjadi kesalahan server: {str(e)}', 'danger')
        finally:
            conn.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if session.get('user_role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('dashboard.html')

# --- MODUL DASHBOARD ADMIN (TAHAP 5) ---

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Halaman Dashboard Utama Administrator dengan Ringkasan Statistik."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Total Pendapatan dari Pembayaran Lunas
            cursor.execute("SELECT SUM(amount) as total_revenue FROM payments WHERE payment_status = 'paid'")
            rev_res = cursor.fetchone()
            total_revenue = rev_res['total_revenue'] if rev_res and rev_res['total_revenue'] else 0.0

            # 2. Total Reservasi Keseluruhan
            cursor.execute("SELECT COUNT(*) as total_reservations FROM reservations")
            total_reservations = cursor.fetchone()['total_reservations']

            # 3. Jumlah Kamar Tersedia & Kamar Dipesan/Dipakai
            cursor.execute("SELECT COUNT(*) as total_rooms FROM rooms")
            total_rooms = cursor.fetchone()['total_rooms']

            cursor.execute("SELECT COUNT(*) as checked_in_count FROM reservations WHERE status = 'checked_in'")
            checked_in_count = cursor.fetchone()['checked_in_count']

            cursor.execute("SELECT COUNT(*) as pending_count FROM reservations WHERE status = 'pending'")
            pending_count = cursor.fetchone()['pending_count']

            # 4. Reservasi Terbaru (5 Terakhir)
            sql_recent = """
                SELECT r.*, rm.room_number, rm.room_type, u.name as guest_name, p.payment_status
                FROM reservations r
                JOIN rooms rm ON r.room_id = rm.id
                JOIN users u ON r.user_id = u.id
                LEFT JOIN payments p ON r.id = p.reservation_id
                ORDER BY r.created_at DESC LIMIT 5
            """
            cursor.execute(sql_recent)
            recent_reservations = cursor.fetchall()
    except Exception as e:
        total_revenue = 0.0
        total_reservations = 0
        total_rooms = 0
        checked_in_count = 0
        pending_count = 0
        recent_reservations = []
        flash(f'Gagal memuat statistik admin: {str(e)}', 'danger')
    finally:
        conn.close()

    return render_template(
        'admin_dashboard.html',
        total_revenue=total_revenue,
        total_reservations=total_reservations,
        total_rooms=total_rooms,
        checked_in_count=checked_in_count,
        pending_count=pending_count,
        recent_reservations=recent_reservations
    )

@app.route('/admin/rooms', methods=['GET', 'POST'])
@admin_required
def admin_rooms():
    """Kelola Kamar: Daftar, Tambah, Edit, Hapus Kamar."""
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            room_number = request.form.get('room_number', '').strip()
            room_type = request.form.get('room_type', '').strip()
            price_per_night = request.form.get('price_per_night', '').strip()
            capacity = request.form.get('capacity', '').strip()
            facilities = request.form.get('facilities', '').strip()
            status = request.form.get('status', 'available')

            if not room_number or not room_type or not price_per_night or not capacity:
                flash('Nomor, Tipe, Harga, dan Kapasitas kamar wajib diisi.', 'danger')
            else:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM rooms WHERE room_number = %s", (room_number,))
                    if cursor.fetchone():
                        flash('Nomor kamar sudah ada dalam sistem.', 'danger')
                    else:
                        cursor.execute(
                            """INSERT INTO rooms (room_number, room_type, price_per_night, capacity, facilities, status)
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (room_number, room_type, float(price_per_night), int(capacity), facilities, status)
                        )
                        flash('Kamar baru berhasil ditambahkan!', 'success')
            return redirect(url_for('admin_rooms'))

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM rooms ORDER BY room_number ASC")
            rooms_list = cursor.fetchall()
    except Exception as e:
        rooms_list = []
        flash(f'Terjadi kesalahan server: {str(e)}', 'danger')
    finally:
        conn.close()

    return render_template('admin_rooms.html', rooms=rooms_list)

@app.route('/admin/rooms/edit/<int:room_id>', methods=['POST'])
@admin_required
def admin_edit_room(room_id):
    """Proses Pembaruan Data Kamar."""
    room_number = request.form.get('room_number', '').strip()
    room_type = request.form.get('room_type', '').strip()
    price_per_night = request.form.get('price_per_night', '').strip()
    capacity = request.form.get('capacity', '').strip()
    facilities = request.form.get('facilities', '').strip()
    status = request.form.get('status', 'available')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """UPDATE rooms 
                   SET room_number = %s, room_type = %s, price_per_night = %s, capacity = %s, facilities = %s, status = %s
                   WHERE id = %s""",
                (room_number, room_type, float(price_per_night), int(capacity), facilities, status, room_id)
            )
            flash('Data kamar berhasil diperbarui.', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui kamar: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin_rooms'))

@app.route('/admin/rooms/delete/<int:room_id>', methods=['POST'])
@admin_required
def admin_delete_room(room_id):
    """Proses Penghapusan Kamar."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
            flash('Kamar berhasil dihapus.', 'info')
    except Exception as e:
        flash(f'Gagal menghapus kamar: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin_rooms'))

@app.route('/admin/reservations')
@admin_required
def admin_reservations():
    """Kelola Reservasi: Operasional Check-In, Check-Out, & Status Reservasi."""
    status_filter = request.args.get('status', '').strip()

    sql = """
        SELECT r.*, rm.room_number, rm.room_type, u.name as guest_name, u.email as guest_email, p.payment_status
        FROM reservations r
        JOIN rooms rm ON r.room_id = rm.id
        JOIN users u ON r.user_id = u.id
        LEFT JOIN payments p ON r.id = p.reservation_id
        WHERE 1=1
    """
    params = []

    if status_filter:
        sql += " AND r.status = %s"
        params.append(status_filter)

    sql += " ORDER BY r.created_at DESC"

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            reservations_list = cursor.fetchall()
    except Exception as e:
        reservations_list = []
        flash(f'Gagal memuat data reservasi: {str(e)}', 'danger')
    finally:
        conn.close()

    return render_template('admin_reservations.html', reservations=reservations_list, selected_status=status_filter)

@app.route('/admin/reservations/check-in/<int:booking_id>', methods=['POST'])
@admin_required
def admin_check_in(booking_id):
    """Proses Check-In Tamu oleh Admin."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM reservations WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()

            if not booking:
                flash('Pesanan tidak ditemukan.', 'danger')
                return redirect(url_for('admin_reservations'))

            cursor.execute("UPDATE reservations SET status = 'checked_in' WHERE id = %s", (booking_id,))
            cursor.execute("UPDATE rooms SET status = 'booked' WHERE id = %s", (booking['room_id'],))

            flash(f'Tamu untuk reservasi #RES-{booking_id} berhasil CHECK-IN.', 'success')
    except Exception as e:
        flash(f'Gagal memproses check-in: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin_reservations'))

@app.route('/admin/reservations/check-out/<int:booking_id>', methods=['POST'])
@admin_required
def admin_check_out(booking_id):
    """Proses Check-Out Tamu oleh Admin."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM reservations WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()

            if not booking:
                flash('Pesanan tidak ditemukan.', 'danger')
                return redirect(url_for('admin_reservations'))

            cursor.execute("UPDATE reservations SET status = 'checked_out' WHERE id = %s", (booking_id,))
            cursor.execute("UPDATE rooms SET status = 'available' WHERE id = %s", (booking['room_id'],))

            flash(f'Tamu untuk reservasi #RES-{booking_id} berhasil CHECK-OUT. Kamar kembali tersedia.', 'success')
    except Exception as e:
        flash(f'Gagal memproses check-out: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin_reservations'))

@app.route('/admin/reports')
@admin_required
def admin_reports():
    """Laporan Pendapatan & Rekapitulasi Reservasi."""
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    sql = """
        SELECT r.*, rm.room_number, rm.room_type, u.name as guest_name, p.payment_status, p.payment_method, p.payment_date
        FROM reservations r
        JOIN rooms rm ON r.room_id = rm.id
        JOIN users u ON r.user_id = u.id
        LEFT JOIN payments p ON r.id = p.reservation_id
        WHERE 1=1
    """
    params = []

    if start_date:
        sql += " AND DATE(r.created_at) >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND DATE(r.created_at) <= %s"
        params.append(end_date)

    sql += " ORDER BY r.created_at DESC"

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            reports = cursor.fetchall()

            sql_sum = "SELECT SUM(r.total_price) as total_income FROM reservations r JOIN payments p ON r.id = p.reservation_id WHERE p.payment_status = 'paid'"
            params_sum = []
            if start_date:
                sql_sum += " AND DATE(r.created_at) >= %s"
                params_sum.append(start_date)
            if end_date:
                sql_sum += " AND DATE(r.created_at) <= %s"
                params_sum.append(end_date)

            cursor.execute(sql_sum, params_sum)
            inc_res = cursor.fetchone()
            total_income = inc_res['total_income'] if inc_res and inc_res['total_income'] else 0.0

    except Exception as e:
        reports = []
        total_income = 0.0
        flash(f'Gagal memuat laporan: {str(e)}', 'danger')
    finally:
        conn.close()

    return render_template('admin_reports.html', reports=reports, total_income=total_income, start_date=start_date, end_date=end_date)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
