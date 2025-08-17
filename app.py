from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from dotenv import load_dotenv
import certifi
from bson import ObjectId

app = Flask(__name__)
load_dotenv()

secretKey = os.getenv("secretKey")
app.secret_key = secretKey
client = MongoClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
db = client["EchoChats"]
users = db["users"]
dbComments = db["dbComments"]
header_text = "Nexus Learn" # change text here to change h1 in Comments section for your app/embed
#nest get_port: 34941

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

COMMENTS_PER_PAGE = 5

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    return render_template("home.html")


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        file = request.files.get('profile_pic')

        if not file or not allowed_file(file.filename):
            flash("Please upload a valid image file (png, jpg, jpeg, gif)")
            return redirect(url_for('signup'))

        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        profile_pic_url = f"/{file_path}"

        existing_user = users.find_one({"username": username})
        if existing_user:
            flash("Username already exists")
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        users.insert_one({
            "email": email,
            "username": username,
            "password": hashed_password,
            "profile_pic": profile_pic_url
        })

        flash("Signup successful, you can now log in")
        return redirect(url_for('index'))

    return render_template('signup.html')

@app.route("/user")
def user_profile():
    if "username" not in session:
        flash("Please log in to view your profile")
        return redirect(url_for("login"))

    user = users.find_one({"username": session["username"]})
    return render_template("user.html", user=user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = users.find_one({"username": username})
        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            flash("Login successful!")
            return redirect(url_for('home'))
        else:
            flash("Invalid username or password")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/change_profile_pic', methods=['POST'])
def change_profile_pic():
    if "username" not in session:
        flash("Please log in first")
        return redirect(url_for("login"))

    file = request.files.get('new_profile_pic')
    if not file:
        flash("No file uploaded")
        return redirect(url_for('user_profile'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        profile_pic_url = f"/{file_path}"
        users.update_one({"username": session["username"]}, {"$set": {"profile_pic": profile_pic_url}})
        flash("Profile picture updated successfully!")
    else:
        flash("Invalid file type")

    return redirect(url_for('user_profile'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("You have been logged out")
    return redirect(url_for('login'))

@app.route('/delete_account', methods=['POST'])
def delete_account():
    if "username" not in session:
        flash("Please log in first")
        return redirect(url_for("login"))

    users.delete_one({"username": session["username"]})
    session.pop("username", None)
    flash("Your account has been deleted.")
    return redirect(url_for("signup"))

@app.route('/comments')
def comments_page():
    return render_template('comments.html', header_text=header_text)

@app.route('/api/comments', methods=['GET', 'POST'])
def handle_comments():
    if request.method == 'POST':
        if "username" not in session:
            return jsonify({"error": "Login required"}), 403

        data = request.json
        comment = {
            "username": session["username"],
            "content": data.get("content"),
            "likes": 0,
            "replies": [],
            "profile_pic": users.find_one({"username": session["username"]})["profile_pic"]
        }
        result = dbComments.insert_one(comment)
        comment["_id"] = str(result.inserted_id) 
        return jsonify({"message": "Comment added", "comment": comment})

    # Added lazy loading for comments here lazy loading (And in html)
    page = int(request.args.get("page", 1))
    skip = (page - 1) * COMMENTS_PER_PAGE
    comments = list(dbComments.find().skip(skip).limit(COMMENTS_PER_PAGE))
    for c in comments:
        c["_id"] = str(c["_id"])  
        if "replies" in c:
            for r in c["replies"]:
                if "_id" in r:
                    r["_id"] = str(r["_id"])
    return jsonify(comments)

@app.route('/api/like_comment', methods=['POST'])
def like_comment():
    data = request.json
    comment_id = data.get("comment_id")
    if not comment_id:
        return jsonify({"error": "No comment ID"}), 400
    dbComments.update_one({"_id": ObjectId(comment_id)}, {"$inc": {"likes": 1}})
    return jsonify({"message": "Liked"})

@app.route('/api/delete_comment', methods=['POST'])
def delete_comment():
    if "username" not in session:
        return jsonify({"error": "Login required"}), 403
    data = request.json
    comment_id = data.get("comment_id")
    comment = dbComments.find_one({"_id": ObjectId(comment_id)})

    if comment and comment["username"] == session["username"]:
        dbComments.delete_one({"_id": ObjectId(comment_id)})
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Not authorized"}), 403


@app.route('/api/reply', methods=['POST'])
def reply_comment():
    if "username" not in session:
        return jsonify({"error": "Login required"}), 403

    data = request.json
    comment_id = data.get("comment_id")
    reply_content = data.get("reply")
    reply = {
        "username": session["username"],
        "content": reply_content,
        "likes": 0,
        "profile_pic": users.find_one({"username": session["username"]})["profile_pic"]
    }
    dbComments.update_one({"_id": ObjectId(comment_id)}, {"$push": {"replies": reply}})
    return jsonify({"message": "Reply added", "reply": reply})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=32953, debug=True)