from flask import Flask, render_template, request, redirect, url_for, flash, Blueprint
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
import re
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import timedelta
from datetime import datetime

app = Flask(__name__)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False   # Change to True when using HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100/day", "20/hour"]
)

app.config['SECRET_KEY'] = 'skillhub-secret'
app.config['MYSQL_HOST'] = 'crotchet.mysql.pythonanywhere-services.com'
app.config['MYSQL_USER'] = 'crotchet'
app.config['MYSQL_PASSWORD'] = 'd37f705c269'
app.config['MYSQL_DB'] = 'crotchet$skillhub'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

class User(UserMixin):
    def __init__(self, id, full_name, email, is_verified):
        self.id = id
        self.full_name = full_name
        self.email = email
        self.is_verified = is_verified


@login_manager.user_loader
def load_user(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    u = cur.fetchone()
    cur.close()
    if u:
        return User(u['id'], u['full_name'], u['email'], u['is_verified'])
    return None

@app.context_processor
def inject_global_data():
    cur = mysql.connection.cursor()
    
    # 1. Fetch categories
    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()

    # 2. Fetch stats
    cur.execute("SELECT COUNT(*) AS total FROM users WHERE is_verified = 1")
    student_count = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM bookings WHERE status = 'completed'")
    booking_count = cur.fetchone()['total']

    cur.execute("SELECT ROUND(AVG(rating),1) AS avg FROM reviews")
    row = cur.fetchone()
    avg_rating = row['avg'] if row['avg'] else 4.9

    cur.close()

    return {
        'categories': categories,
        'stats': {
            "students": student_count,
            "bookings": booking_count,
            "rating": avg_rating
        }
    }

main = Blueprint('main', __name__)

def is_strong_password(password):
    """
    Password must contain:
    - Minimum 8 characters
    - One uppercase
    - One lowercase
    - One number
    - One special character
    """
    pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#!]).{8,}$'
    return re.match(pattern, password)

@main.route('/')
def index():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.id, u.full_name, s.title, s.price_per_hour, c.name AS category_name,
               u.course, u.year_of_study, s.tags, s.id AS skill_id
        FROM skills s
        JOIN users u ON u.id = s.user_id
        JOIN categories c ON c.id = s.category_id
        LIMIT 3
    """)
    featured = cur.fetchall()
    cur.close()

    return render_template('home.html', featured=featured)
    # cur.execute("SELECT COUNT(*) AS total FROM users WHERE is_verified = 1")
    # student_count = cur.fetchone()['total']

    # cur.execute("SELECT COUNT(*) AS total FROM bookings WHERE status = 'completed'")
    # booking_count = cur.fetchone()['total']

    # cur.execute("SELECT ROUND(AVG(rating),1) AS avg FROM reviews")
    # row = cur.fetchone()
    # avg_rating = row['avg'] if row['avg'] else 4.9

   


@main.route('/search')
def search():
    # 1. Grab filter arguments passed from search.html
    query = request.args.get('q', '').strip()
    selected_category = request.args.get('category', '').strip()

    cur = mysql.connection.cursor()

    # 2. Base SQL Query
    sql = """
        SELECT 
            u.id,
            u.full_name,
            u.course,
            u.year_of_study,
            s.id AS skill_id,
            s.title,
            s.description,
            s.price_per_hour, 
            c.name AS category_name,
            ROUND(AVG(r.rating),1) AS avg_rating,
            COUNT(r.id) AS review_count
        FROM skills s
        JOIN users u ON u.id = s.user_id
        JOIN categories c ON c.id = s.category_id
        LEFT JOIN reviews r ON r.reviewee_id = u.id
        WHERE 1=1
    """
    params = []

    # 3. Apply Dynamic Filters if they exist
    if query:
        sql += " AND (s.title LIKE %s OR s.description LIKE %s)"
        params.extend([f"%{query}%", f"%{query}%"])

    if selected_category:
        sql += " AND c.slug = %s"
        params.append(selected_category)

    sql += " GROUP BY u.id, s.id, c.id ORDER BY s.id DESC"
    
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()

    return render_template(
        "search.html", 
        results=rows, 
        query=query, 
        selected_category=selected_category
    )



auth = Blueprint('auth', __name__)


# @auth.route('/register', methods=['GET', 'POST'])
# def register():
#     if request.method == 'POST':
#         full_name = request.form['full_name']
#         email = request.form['email']
#         password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

#         course = request.form['course']
#         year_of_study = request.form['year_of_study']

#         cur = mysql.connection.cursor()
#         cur.execute("""
#             INSERT INTO users(full_name, email, password_hash, course, year_of_study, is_verified)
#             VALUES(%s,%s,%s,%s,%s,1)
#         """, (full_name, email, password, course, year_of_study))

#         mysql.connection.commit()
#         cur.close()

#         return redirect(url_for('auth.login'))

#     return render_template('register.html')
@auth.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        full_name = request.form['full_name'].strip()
        phone = request.form["phone"]
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        course = request.form['course']
        year_of_study = request.form['year_of_study']

        # Only Kabarak emails
        if not email.endswith("@kabarak.ac.ke"):
            flash("Please use your Kabarak University email.", "danger")
            return redirect(url_for('auth.register'))

        # Passwords match
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for('auth.register'))

        # Strong password
        if not is_strong_password(password):
            flash(
                "Password must contain at least 8 characters, an uppercase letter, a lowercase letter, a number and a special character.",
                "danger"
            )
            return redirect(url_for('auth.register'))

        cur = mysql.connection.cursor()

        # Duplicate email
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        existing = cur.fetchone()

        if existing:
            cur.close()
            flash("This email is already registered.", "danger")
            return redirect(url_for('auth.register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        cur.execute("""
            INSERT INTO users
            (full_name,phone,email,password_hash,course,year_of_study,is_verified)
            VALUES(%s,%s,%s,%s,%s,%s,%s)
        """, (
            full_name,
            phone,
            email,
            hashed_password,
            course,
            year_of_study,
            1
        ))

        mysql.connection.commit()
        cur.close()

        flash("Account created successfully. Please login.", "success")
        return redirect(url_for('auth.login'))

    return render_template('register.html')

# @auth.route('/login', methods=['GET', 'POST'])
# def login():
#     if request.method == 'POST':
#         email = request.form['email']
#         password = request.form['password']

#         cur = mysql.connection.cursor()
#         cur.execute("SELECT * FROM users WHERE email=%s", (email,))
#         u = cur.fetchone()
#         cur.close()

#         if u and bcrypt.check_password_hash(u['password_hash'], password):
#             login_user(User(u['id'], u['full_name'], u['email'], u['is_verified']))
#             return redirect(url_for('main.index'))

#         flash("Invalid login")

#     return render_template('login.html')
@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():

    if request.method == 'POST':

        email = request.form['email'].strip().lower()
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        u = cur.fetchone()
        cur.close()

        if u and bcrypt.check_password_hash(u['password_hash'], password):

            login_user(
                User(
                    u['id'],
                    u['full_name'],
                    u['email'],
                    u['is_verified']
                ),
                remember=True
            )

            flash("Welcome back!", "success")
            return redirect(url_for('main.index'))

        flash("Invalid email or password.", "danger")

    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


skills_bp = Blueprint('skills_bp', __name__)


@skills_bp.route('/skills/<int:skill_id>')
def detail(skill_id):
    cur = mysql.connection.cursor()

    # Get skill details
    cur.execute("""
        SELECT
            s.*,
            u.full_name,
            u.course,
            u.year_of_study,
            u.bio,
            c.name AS category_name
        FROM skills s
        JOIN users u ON u.id = s.user_id
        JOIN categories c ON c.id = s.category_id
        WHERE s.id = %s
    """, (skill_id,))

    skill = cur.fetchone()

    if not skill:
        cur.close()
        flash("Skill not found.", "danger")
        return redirect(url_for("main.search"))

    # Get reviews
    cur.execute("""
        SELECT
            r.*,
            u.full_name
        FROM reviews r
        JOIN users u ON u.id = r.reviewer_id
        WHERE r.skill_id = %s
        ORDER BY r.created_at DESC
    """, (skill_id,))

    reviews = cur.fetchall()

    # Get average rating
    cur.execute("""
        SELECT
            ROUND(AVG(rating), 1) AS avg_rating,
            COUNT(*) AS total_reviews
        FROM reviews
        WHERE skill_id = %s
    """, (skill_id,))

    rating = cur.fetchone()

    avg_rating = rating["avg_rating"]
    total_reviews = rating["total_reviews"]

    cur.close()

    return render_template(
        "skill_detail.html",
        skill=skill,
        reviews=reviews,
        avg_rating=avg_rating,
        total_reviews=total_reviews
    )


@skills_bp.route('/skills/post', methods=['GET', 'POST'])
@login_required
def post_skill():

    if request.method == 'POST':
        title = request.form['title']
        category_id = request.form['category_id']
        desc = request.form['description']
        tags = request.form.get('tags', '')
        price = request.form['price_per_hour']

        print(request.form)   # <-- Temporary, for debugging

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO skills
            (user_id, category_id, title, description, tags, price_per_hour)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            current_user.id,
            category_id,
            title,
            desc,
            tags,
            price
        ))

        mysql.connection.commit()
        cur.close()

        flash("Skill posted successfully!")
        return redirect(url_for('main.index'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()
    cur.close()

    return render_template("post_skill.html", categories=categories)

bookings_bp = Blueprint('bookings_bp', __name__)
reviews_bp = Blueprint('reviews_bp', __name__)


@bookings_bp.route('/book/<int:skill_id>', methods=['GET', 'POST'])
@login_required
def book(skill_id):
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM skills WHERE id=%s", (skill_id,))
    skill = cur.fetchone()

    if request.method == 'POST':

        scheduled_at = request.form.get("scheduled_at")

        if not scheduled_at:
            flash("Please select a booking date and time.", "error")
            return redirect(url_for("bookings_bp.book", skill_id=skill_id))

        booking_time = datetime.strptime(scheduled_at, "%Y-%m-%dT%H:%M")

        if booking_time <= datetime.now():
            flash("You cannot book a session in the past.", "error")
            return redirect(url_for("bookings_bp.book", skill_id=skill_id))

        hours = float(request.form['hours'])
        total = hours * float(skill['price_per_hour'])
        provider_id = skill['user_id']

        if provider_id == current_user.id:
            flash("You cannot book your own skill.", "danger")
            cur.close()
            return redirect(url_for("skills_bp.detail", skill_id=skill_id))

        cur.execute("""
            INSERT INTO bookings(
                skill_id,
                client_id,
                provider_id,
                hours,
                scheduled_at,
                total_amount
            )
            VALUES(%s,%s,%s,%s,%s,%s)
        """, (
            skill_id,
            current_user.id,
            provider_id,
            hours,
            booking_time,
            total
        ))

        mysql.connection.commit()
        cur.close()

        flash("Booked successfully!")
        return redirect(url_for('bookings_bp.my_bookings'))

    cur.close()
    return render_template('book.html', skill=skill)


@skills_bp.route('/my-skills')
@login_required
def my_skills():

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            s.*,
            c.name AS category_name
        FROM skills s
        JOIN categories c
            ON s.category_id = c.id
        WHERE s.user_id = %s
        ORDER BY s.id DESC
    """, (current_user.id,))

    skills = cur.fetchall()
    cur.close()

    return render_template("my_skills.html", skills=skills)

@skills_bp.route('/skills/edit/<int:skill_id>', methods=['GET', 'POST'])
@login_required
def edit_skill(skill_id):

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT *
        FROM skills
        WHERE id=%s AND user_id=%s
    """, (skill_id, current_user.id))

    skill = cur.fetchone()

    if not skill:
        cur.close()
        flash("Skill not found.", "danger")
        return redirect(url_for("skills_bp.my_skills"))

    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()

    if request.method == "POST":

        title = request.form["title"]
        category = request.form["category_id"]
        description = request.form["description"]
        tags = request.form["tags"]
        price = request.form["price_per_hour"]

        cur.execute("""
            UPDATE skills
            SET
                title=%s,
                category_id=%s,
                description=%s,
                tags=%s,
                price_per_hour=%s
            WHERE id=%s
        """, (
            title,
            category,
            description,
            tags,
            price,
            skill_id
        ))

        mysql.connection.commit()
        cur.close()

        flash("Skill updated successfully!", "success")

        return redirect(url_for("skills_bp.my_skills"))

    cur.close()

    return render_template(
        "edit_skill.html",
        skill=skill,
        categories=categories
    )


@skills_bp.route('/skills/delete/<int:skill_id>', methods=['POST'])
@login_required
def delete_skill(skill_id):

    cur = mysql.connection.cursor()

    cur.execute("""
        DELETE FROM skills
        WHERE id=%s
        AND user_id=%s
    """, (
        skill_id,
        current_user.id
    ))

    mysql.connection.commit()

    cur.close()

    flash("Skill deleted successfully.", "success")

    return redirect(url_for("skills_bp.my_skills"))


@bookings_bp.route('/my')
@login_required
def my_bookings():
    cur = mysql.connection.cursor()

    # BOOKINGS AS CLIENT
    cur.execute("""
        SELECT 
            b.*,
            s.title AS skill_title,
            u.full_name AS provider_name,
            c.name AS category_name,
            u.phone,
            u.email,
                
            EXISTS(
            SELECT 1
            FROM reviews r
            WHERE r.booking_id = b.id
        ) AS reviewed
        FROM bookings b
        JOIN skills s ON s.id = b.skill_id
        JOIN users u ON u.id = b.provider_id
        JOIN categories c ON c.id = s.category_id
        WHERE b.client_id = %s
        ORDER BY b.id DESC
    """, (current_user.id,))
    as_client = cur.fetchall()

    # BOOKINGS AS PROVIDER
    cur.execute("""
        SELECT 
            b.*,
            s.title AS skill_title,
            u.full_name AS client_name
        FROM bookings b
        JOIN skills s ON s.id = b.skill_id
        JOIN users u ON u.id = b.client_id
        WHERE b.provider_id = %s
        ORDER BY b.id DESC
    """, (current_user.id,))
    as_provider = cur.fetchall()

    cur.close()

    return render_template(
        'my_bookings.html',
        as_client=as_client,
        as_provider=as_provider
    )


@bookings_bp.route('/update/<int:booking_id>/<status>')
@login_required
def update_status(booking_id, status):
    cur = mysql.connection.cursor()
    cur.execute("UPDATE bookings SET status=%s WHERE id=%s",
                (status, booking_id))
    mysql.connection.commit()
    cur.close()

    return redirect(url_for('bookings_bp.my_bookings'))


@reviews_bp.route('/review/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def add_review(booking_id):

    cur = mysql.connection.cursor()

    # Check that this booking belongs to the logged in client
    cur.execute("""
        SELECT
            b.*,
            s.title,
            s.id AS skill_id,
            u.full_name AS provider_name
        FROM bookings b
        JOIN skills s
            ON s.id=b.skill_id
        JOIN users u
            ON u.id=b.provider_id
        WHERE
            b.id=%s
            AND b.client_id=%s
            AND b.status='completed'
    """,(booking_id,current_user.id))

    booking = cur.fetchone()

    if not booking:
        flash("This booking cannot be reviewed.","danger")
        cur.close()
        return redirect(url_for("bookings_bp.my_bookings"))

    # Prevent duplicate reviews
    cur.execute("""
        SELECT id
        FROM reviews
        WHERE booking_id=%s
    """,(booking_id,))

    exists = cur.fetchone()

    if exists:
        flash("You already reviewed this booking.","warning")
        cur.close()
        return redirect(url_for("bookings_bp.my_bookings"))

    if request.method=="POST":

        rating = int(request.form["rating"])
        comment = request.form["comment"]

        if rating < 1 or rating > 5:
            flash("Rating must be between 1 and 5.","danger")
            return redirect(url_for("reviews_bp.add_review",
                                    booking_id=booking_id))

        cur.execute("""
            INSERT INTO reviews
            (
                booking_id,
                reviewer_id,
                reviewee_id,
                skill_id,
                rating,
                comment
            )
            VALUES
            (%s,%s,%s,%s,%s,%s)
        """,(
            booking_id,
            current_user.id,
            booking["provider_id"],
            booking["skill_id"],
            rating,
            comment
        ))

        mysql.connection.commit()

        flash("Thank you for your review!","success")

        cur.close()

        return redirect(url_for("skills_bp.detail",
                                skill_id=booking["skill_id"]))

    cur.close()

    return render_template(
        "review.html",
        booking=booking
    )

app.register_blueprint(main)
app.register_blueprint(auth)
app.register_blueprint(skills_bp)
app.register_blueprint(bookings_bp)
app.register_blueprint(reviews_bp)

if __name__ == '__main__':
    app.run(debug=True)