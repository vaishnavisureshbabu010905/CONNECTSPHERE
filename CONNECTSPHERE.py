from flask import Flask , render_template , request , flash , redirect , url_for , session , send_file
from flask import Response
from flask_mysqldb import MySQL
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash , check_password_hash
from werkzeug.utils import secure_filename
import os
from io import BytesIO

load_dotenv()
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

posts = []

app = Flask(__name__)

app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

mysql = MySQL(app)

# @app.route('/home_page')
# def home_page():
#     if "user_id" not in session:
#         flash("Please log in first!", "warning")
#         return redirect(url_for('login'))
#     cur = mysql.connection.cursor()
#     cur.execute("SELECT name, username, email FROM user WHERE id=%s", (session["user_id"],))
#     user_details = cur.fetchone()
#     cur.close()
#     return render_template('home.html', user=user_details)  

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/submit_login' , methods=['POST'])
def login_submit():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM user WHERE username=%s AND email=%s",(username,email))
    current_user=cur.fetchone()
    if current_user and check_password_hash(current_user[4], password):
        session["user_id"] = current_user[0]
        flash("Successfully logged in")
        return redirect(url_for('feed'))
    else:
        flash("Details didnt match")
        return render_template('login.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/submit_signup' , methods=['POST'])
def signup_submit():
    name = request.form['name']
    username = request.form['username']
    email = request.form['email']
    password = generate_password_hash(request.form['password'])
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM user WHERE username=%s OR email=%s",(username,email))
    existing_user=cur.fetchone() 
    if(existing_user):
        flash("Username or Email already exists. Try a different one.", "danger")
        return render_template('signup.html') 
    cur.execute("INSERT INTO user (name, username, email, password) VALUES (%s, %s, %s, %s)",(name, username, email, password))
    mysql.connection.commit()
    cur.close
    return redirect(url_for('login'))

@app.route('/feed')
def feed():
    user_id = session['user_id']
    cursor = mysql.connection.cursor()

    # Get all accepted friends (both directions)
    cursor.execute("""
        SELECT collab_id AS friend_id 
        FROM collab 
        WHERE user_id = %s AND status = 'accepted'
        UNION
        SELECT user_id AS friend_id 
        FROM collab 
        WHERE collab_id = %s AND status = 'accepted'
    """, (user_id, user_id))
    
    friends = [row[0] for row in cursor.fetchall()]  # list of friend_ids from tuple

    enriched_posts = []

    if friends:
        format_strings = ','.join(['%s'] * len(friends))
        query = f"""
        SELECT posts.id, posts.filename, posts.caption, posts.user_id, user.username
        FROM posts
        JOIN user ON posts.user_id = user.id
        WHERE posts.user_id IN ({format_strings})
        ORDER BY posts.id DESC
        """
        cursor.execute(query, tuple(friends))
        raw_posts = cursor.fetchall()

        for post in raw_posts:
            post_id = post[0]
            filename = post[1]
            caption = post[2]
            post_user_id = post[3]
            username = post[4]

            # Like count
            cursor.execute("SELECT COUNT(*) FROM likes WHERE post_id = %s", (post_id,))
            like_count = cursor.fetchone()[0]

            # Did current user like?
            cursor.execute("SELECT 1 FROM likes WHERE post_id = %s AND user_id = %s", (post_id, user_id))
            liked_by_user = cursor.fetchone() is not None

            # Comments
            cursor.execute("SELECT comment FROM comments WHERE post_id = %s", (post_id,))
            comments = [row[0] for row in cursor.fetchall()]

            # Build enriched post
            enriched_posts.append({
                'id': post_id,
                'filename': filename,
                'caption': caption,
                'user_id': post_user_id,
                'username': username,
                'like_count': like_count,
                'liked_by_user': liked_by_user,
                'comments': comments
            })

    cursor.close()
    return render_template('feed.html', posts=enriched_posts)




@app.route('/search_page')
def search_page():
    return render_template('search.html')

@app.route('/search', methods=['GET', 'POST'])
def search():
    if "user_id" not in session:
        flash("Please log in first!", "warning")
        return redirect(url_for('login'))

    results = []
    if request.method == 'POST':
        query = request.form['query']
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, email FROM user WHERE username LIKE %s AND id != %s", 
                    ('%' + query + '%', session['user_id']))
        results = cur.fetchall()
        cur.close()

    return render_template('search.html', results=results)

@app.route('/profpage/<int:user_id>')
def profpage(user_id):
    print("the id is", user_id)
    cursor = mysql.connection.cursor()

    # Get user info
    cursor.execute("SELECT name, username, email, id FROM user WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    # Check collab status
    cursor.execute("""
        SELECT status FROM collab 
        WHERE (user_id = %s AND collab_id = %s) OR (user_id = %s AND collab_id = %s)
    """, (session['user_id'], user_id, user_id, session['user_id']))
    status_row = cursor.fetchone()
    is_friend = status_row and status_row[0] == 'accepted'
    is_pending = status_row and status_row[0] == 'pending'   

    enriched_images = []

    # Only get posts if they are friends
    if is_friend:
        cursor.execute("SELECT id, filename, caption FROM posts WHERE user_id = %s", (user_id,))
        raw_images = cursor.fetchall()

        for image in raw_images:
            post_id = image[0]

            # Like count
            cursor.execute("SELECT COUNT(*) FROM likes WHERE post_id = %s", (post_id,))
            like_count = cursor.fetchone()[0]

            # Did current user like?
            cursor.execute("SELECT 1 FROM likes WHERE post_id = %s AND user_id = %s", (post_id, session['user_id']))
            liked_by_user = cursor.fetchone() is not None

            # Comments
            cursor.execute("SELECT comment FROM comments WHERE post_id = %s", (post_id,))
            comments = cursor.fetchall()

            enriched_images.append({
                'id': post_id,
                'filename': image[1],
                'caption': image[2],
                'like_count': like_count,
                'liked_by_user': liked_by_user,
                'comments': comments
            })

    cursor.close()
    return render_template(
        'profpage.html', 
        user=user, 
        is_friend=is_friend, 
        is_pending=is_pending,
        posts=enriched_images
    )


@app.route('/collab/<int:user_id>')
def collab(user_id):
    results = []
    if "user_id" not in session:
        flash("Please log in first!", "warning")
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM collab WHERE user_id=%s AND collab_id=%s", 
                (session["user_id"], user_id))
    if not cur.fetchone():
        cur.execute("INSERT INTO collab (user_id, collab_id , status) VALUES (%s, %s ,'pending')", 
                    (session["user_id"], user_id))
        mysql.connection.commit()
        flash("Now Collaborated!", "success")
        cur.execute("SELECT * FROM user WHERE id = %s",(user_id,))
        results = cur.fetchone()
        cur.close()
        return redirect(url_for('profpage', user_id=user_id))
    else:
        flash("Already following this user.", "info")
        cur.execute("SELECT * FROM user WHERE id = %s",(user_id,))
        results = cur.fetchone()
        cur.close()
        return redirect(url_for('profpage', user_id=user_id))
    

@app.route('/collab_requests')
def collab_requests():
    if "user_id" not in session:
        flash("Please log in first!", "warning")
        return redirect(url_for('login'))
    user_id = session.get("user_id")
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT u.id , u.username, u.name
        FROM collab fr
        JOIN user u ON fr.user_id = u.id
        WHERE fr.collab_id = %s AND fr.status = 'pending'
    """, (user_id,))
    
    requests = cur.fetchall()
    cur.close()
    return render_template("collab_request.html", requests=requests)

@app.route('/accept_request/<int:request_id>')
def accept_request(request_id):
    if "user_id" not in session:
        flash("Please log in first!", "warning")
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    cur = mysql.connection.cursor()

    # Only update the specific pending request directed to the current user
    cur.execute("""
        UPDATE collab 
        SET status = 'accepted' 
        WHERE user_id = %s AND collab_id = %s AND status = 'pending'
    """, (request_id, current_user_id))

    mysql.connection.commit()
    cur.close()

    flash("Friend request accepted!", "success")
    return redirect(url_for('collab_requests'))


@app.route('/friends')
def friends():
    if "user_id" not in session:
        flash("Please log in first!", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    query = """
        SELECT u.id, u.username, u.email, c.status
        FROM user u
        JOIN collab c 
          ON ((c.user_id = u.id AND c.collab_id = %s) 
              OR (c.collab_id = u.id AND c.user_id = %s))
        WHERE c.status IN ('accepted', 'pending')
    """
    cur.execute(query, (user_id, user_id))
    friends = cur.fetchall()
    cur.close()

    return render_template('friends.html', friends=friends)

@app.route('/user_profile')
def user_profile():
    user_id = session['user_id']
    print("the id is", user_id)
    cursor = mysql.connection.cursor()

    # Get posts
    cursor.execute("SELECT id, filename, caption FROM posts WHERE user_id = %s", (user_id,))
    raw_images = cursor.fetchall()

    # Get user info
    cursor.execute("SELECT name, username, email, id FROM user WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    enriched_images = []

    for image in raw_images:
        post_id = image[0]

        # Like count
        cursor.execute("SELECT COUNT(*) FROM likes WHERE post_id = %s", (post_id,))
        like_count = cursor.fetchone()[0]

        # Did current user like?
        cursor.execute("SELECT 1 FROM likes WHERE post_id = %s AND user_id = %s", (post_id, user_id))
        liked_by_user = cursor.fetchone() is not None

        # Comments
        cursor.execute("SELECT comment FROM comments WHERE post_id = %s", (post_id,))
        comments = cursor.fetchall()

        # Build new image data
        enriched_images.append({
            'id': post_id,
            'filename': image[1],
            'caption': image[2],
            'like_count': like_count,
            'liked_by_user': liked_by_user,
            'comments': comments
        })

    cursor.close()
    return render_template('user_profile.html', images=enriched_images, user=user)


@app.route("/post", methods=['POST'])
def post():
    user_id = session['user_id']
    if 'image' not in request.files:
        print('No image uploaded!')
        return redirect(url_for('user_profile'))

    file = request.files['image']
    caption = request.form.get('caption', '')

    if file.filename == '':
        print('No file selected!')
        return redirect(url_for('user_profile'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        image_data = file.read()

        cursor =  mysql.connection.cursor()
        cursor.execute("INSERT INTO posts (filename, caption, image_data, user_id) VALUES (%s, %s, %s, %s)",(filename, caption, image_data, user_id))
        mysql.connection.commit()
        cursor.close()
        print('Post uploaded successfully!')
        return redirect(url_for('user_profile'))

    print('Invalid file type!')
    return redirect(url_for('user_profile'))

@app.route("/like/<int:post_id>", methods=['POST'])
def like(post_id):
    user_id = session['user_id']
    cursor =  mysql.connection.cursor()
  
        # Check if user already liked this post
    cursor.execute("SELECT id FROM likes WHERE post_id=%s AND user_id=%s", (post_id, user_id))
    existing = cursor.fetchone()

    if existing:
            # Unlike (remove the like)
        cursor.execute("DELETE FROM likes WHERE id=%s", (existing[0],))
    else:
            # Like
        cursor.execute("INSERT INTO likes (post_id, user_id) VALUES (%s, %s)", (post_id, user_id))

    mysql.connection.commit()
    cursor.close()
    return redirect(url_for('user_profile'))

@app.route("/comment/<int:post_id>", methods=['POST'])
def comment(post_id):
    comment_text = request.form.get('comment', '')
    if not comment_text:
        flash("Comment can't be empty.")
        return redirect(url_for('user_profile'))

    cursor =  mysql.connection.cursor()
    cursor.execute("INSERT INTO comments (post_id, comment) VALUES (%s, %s)", (post_id, comment_text))
    mysql.connection.commit()
    cursor.close()
    return redirect(url_for('user_profile'))

# @app.route('/image/<int:post_id>')
# def serve_image(post_id):
#     cursor =  mysql.connection.cursor()
#     cursor.execute("SELECT image_data, filename FROM posts WHERE id=%s", (post_id,))
#     image = cursor.fetchone()
#     cursor.close()

#     if image:
#         return send_file(BytesIO(image['image_data']), mimetype='image/jpeg', as_attachment=False, download_name=image['filename'])
    return "Image not found", 404

@app.route('/profile-pic/<int:user_id>')
def profile_pic(user_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT profile_pic FROM user WHERE id=%s", (user_id,))
    row = cursor.fetchone()
    cursor.close()

    if row and row[0]:
        return Response(row[0], mimetype='image/jpeg')
    else:
        return '', 404
    
@app.route('/serve_image/<int:post_id>')
def serve_image(post_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT image_data FROM posts WHERE id=%s", (post_id,))
    row = cursor.fetchone()
    cursor.close()

    if row and row[0]:
        return Response(row[0], mimetype='image/jpeg')
    else:
        return '', 404

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/update-settings', methods=['POST'])
def update_settings():
    # theme = request.form.get('theme')
    new_username = request.form.get('username')
    new_password = request.form.get('password')
    profile_pic = request.files.get('profile-pic')

    user_id = session['user_id']# Or use current_user.id if using Flask-Login

    try:
        conn = mysql.connection
        cursor = conn.cursor()

        # Prepare dynamic SQL parts
        sql_parts = []
        values = []

        if new_username:
            sql_parts.append("username=%s")
            values.append(new_username)

        if new_password:
            hashed_password = generate_password_hash(new_password)
            sql_parts.append("password=%s")
            values.append(hashed_password)

        # if theme:
        #     sql_parts.append("theme=%s")
        #     values.append(theme)

        if profile_pic and profile_pic.filename != "":
            image_data = profile_pic.read()
            sql_parts.append("profile_pic=%s")
            values.append(image_data)

        if sql_parts:  # Update only if at least one field is provided
            sql = "UPDATE user SET " + ", ".join(sql_parts) + " WHERE id=%s"
            values.append(user_id)

            cursor.execute(sql, tuple(values))
            conn.commit()
            flash("Settings updated successfully.")
        else:
            flash("No changes made.")

    except Exception as e:
        print("Error:", e)
        flash("Something went wrong!")

    finally:
        try:
            cursor.close()
        except:
            pass

    return redirect(url_for('settings'))

@app.route('/logout')
def logout():
    session.pop("user_id", None)  # ✅ Remove user ID from session
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/delete-account', methods=['POST'])
def delete_account():
    user_id = session['user_id']
    try:
        # Get DB connection from flask_mysqldb's MySQL object
        cur = mysql.connection.cursor()
        print("this is the id", user_id)

        # Delete user
        cur.execute("DELETE FROM user WHERE id = %s", (user_id,))
        mysql.connection.commit()

        cur.close()

        # Log the user out
        flash("Your account has been deleted successfully.", "info")

    except Exception as e:
        print("Error deleting account:", e)
        flash("Something went wrong.", "danger")

    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)