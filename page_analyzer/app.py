from flask import Flask, render_template, request, redirect, flash, get_flashed_messages, url_for
from dotenv import load_dotenv
from urllib.parse import urlparse
from psycopg2.extras import NamedTupleCursor
import os
import psycopg2
import datetime
import validators

app = Flask(__name__)
load_dotenv()
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')


@app.route('/')
def index():
    messages = get_flashed_messages(with_categories=True)
    return render_template(
        'index.html',
        messages=messages
    )


@app.post('/')
def add_url():
    url = request.form.to_dict()['url']
    if not validators.url(url):
        flash('Некорректный URL', 'danger')
        if not url:
            flash('URL обязателен', 'danger')
        elif not validators.length(url, max=255):
            flash('URL превышает 255 символов', 'danger')
        return redirect(url_for('index'), 302)
    normalized_url = normalize(url)
    connection = db_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute("SELECT * FROM urls WHERE name=%s;", (normalized_url, ))
        existed_url = cursor.fetchone()
        if existed_url:
            flash('Страница уже существует', 'info')
            current_id = existed_url.id
        else:
            cursor.execute(
                "INSERT INTO urls (name, created_at) VALUES (%s, %s);",
                (normalized_url, datetime.datetime.now().strftime('%Y-%m-%d'))
            )
            cursor.execute("SELECT * FROM urls WHERE name=%s;", (normalized_url,))
            added_url = cursor.fetchone()
            current_id = added_url.id
            flash('Страница успешно добавлена', 'success')
    connection.close()
    return redirect(url_for('get_url', id=current_id), 302)


@app.route('/urls/<int:id>')
def get_url(id):
    messages = get_flashed_messages(with_categories=True)
    connection = db_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute("SELECT * FROM urls WHERE id=%s;", (id, ))
        url = cursor.fetchone()
    return render_template(
        'url.html',
        url=url,
        messages=messages
    )


@app.route('/urls')
def get_urls():
    connection = db_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute("SELECT * FROM urls ORDER BY id DESC;")
        all_urls = cursor.fetchall()
    connection.close()
    messages = get_flashed_messages(with_categories=True)
    return render_template(
        'urls.html',
        urls=all_urls,
        messages=messages
    )


def db_connect():
    try:
        connection = psycopg2.connect(DATABASE_URL)
        connection.autocommit = True
        return connection
    except:
        return False


def normalize(url):
    url = urlparse(url)
    return f'{url.scheme}://{url.netloc}'


if __name__ == "__main__":
    app.run()

