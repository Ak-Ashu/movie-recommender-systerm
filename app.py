import os
import pickle
import requests
import sqlite3

from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# -------------------- APP SETUP --------------------

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret123")

API_KEY = os.getenv("API_KEY")

# -------------------- LOAD DATA --------------------

movies = pickle.load(open('movies.pkl', 'rb'))
similarity = pickle.load(open('similarity.pkl', 'rb'))

# -------------------- CACHE --------------------

poster_cache = {}
trailer_cache = {}

# -------------------- TMDB FUNCTIONS --------------------

def fetch_poster(movie_id):
    if movie_id in poster_cache:
        return poster_cache[movie_id]

    try:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={API_KEY}"
        data = requests.get(url).json()
        poster_path = data.get('poster_path')

        poster = (
            "https://image.tmdb.org/t/p/w500/" + poster_path
            if poster_path else
            "https://via.placeholder.com/500x750?text=No+Image"
        )

        poster_cache[movie_id] = poster
        return poster
    except:
        return "https://via.placeholder.com/500x750?text=Error"


def fetch_trailer(movie_id):
    if movie_id in trailer_cache:
        return trailer_cache[movie_id]

    try:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={API_KEY}"
        data = requests.get(url).json()

        for video in data.get('results', []):
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                trailer = f"https://www.youtube.com/embed/{video['key']}"
                trailer_cache[movie_id] = trailer
                return trailer
    except:
        pass

    return None

def fetch_movie_details(movie_id):
    try:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={API_KEY}"
        data = requests.get(url).json()

        return {
            "rating": data.get("vote_average", "N/A"),
            "overview": data.get("overview", "No description available")
        }
    except:
        return {
            "rating": "N/A",
            "overview": "No description available"
        }

# -------------------- RECOMMENDATION --------------------
def recommend(movie):
    movie = movie.lower()

    if movie not in movies['title'].str.lower().values:
        return None, [], [], []

    movie_index = movies[movies['title'].str.lower() == movie].index[0]
    distances = similarity[movie_index]

    sorted_movies = sorted(
        list(enumerate(distances)),
        reverse=True,
        key=lambda x: x[1]
    )

    # 🎬 Selected Movie (FIXED INDENTATION)
    selected_idx = sorted_movies[0][0]
    movie_id = movies.iloc[selected_idx].movie_id

    details = fetch_movie_details(movie_id)

    selected = {
        "name": movies.iloc[selected_idx].title,
        "poster": fetch_poster(movie_id),
        "trailer": fetch_trailer(movie_id),
        "rating": details["rating"],
        "overview": details["overview"]
    }

    # 🎥 Similar Movies
    names, posters, trailers = [], [], []

    for i in sorted_movies[1:11]:
        mid = movies.iloc[i[0]].movie_id
        names.append(movies.iloc[i[0]].title)
        posters.append(fetch_poster(mid))
        trailers.append(fetch_trailer(mid))

    return selected, names, posters, trailers

# -------------------- DATABASE --------------------

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS favorites
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  movie TEXT,
                  UNIQUE(username, movie))''')

    conn.commit()
    conn.close()

init_db()

# -------------------- AUTH --------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        except:
            return "User already exists"

        conn.close()
        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user'] = username
            return redirect('/')

        return "Invalid credentials"

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# -------------------- FAVORITES --------------------

@app.route('/add_favorite', methods=['POST'])
def add_favorite():
    if 'user' not in session:
        return redirect('/login')

    movie = request.form['movie']
    user = session['user']

    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    try:
        c.execute("INSERT INTO favorites (username, movie) VALUES (?, ?)", (user, movie))
        conn.commit()
    except:
        pass  # ignore duplicates

    conn.close()
    return redirect('/')

# -------------------- MAIN --------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user' not in session:
        return redirect('/login')

    selected_movie = None
    recommendations = ([], [], [])
    user = session['user']

    if request.method == 'POST':
        movie_name = request.form['movie']
        selected_movie, names, posters, trailers = recommend(movie_name)
        recommendations = (names, posters, trailers)

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT movie FROM favorites WHERE username=?", (user,))
    favorites = [row[0] for row in c.fetchall()]
    conn.close()

    return render_template(
        'index.html',
        movies=movies['title'].values,
        selected_movie=selected_movie,
        recommendations=recommendations,
        user=user,
        favorites=favorites
    )

# -------------------- RUN --------------------

if __name__ == '__main__':
    app.run()